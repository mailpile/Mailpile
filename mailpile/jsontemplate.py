# Copyright (C) 2009 Andy Chu
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Python implementation of json-template.

JSON Template is a minimal and powerful templating language for transforming a
JSON dictionary to arbitrary text.

To use this module, you will typically use the Template constructor, and catch
various exceptions thrown.  You may also want to use the FromFile/FromString
methods, which allow Template constructor options to be embedded in the template
string itself.

Other functions are exposed for tools which may want to process templates.
"""

__author__ = 'Andy Chu'

__all__ = [
    'Error', 'CompilationError', 'EvaluationError', 'BadFormatter',
    'BadPredicate', 'MissingFormatter', 'ConfigurationError',
    'TemplateSyntaxError', 'UndefinedVariable', 'CompileTemplate', 'FromString',
    'FromFile', 'Template', 'expand']

import StringIO
import pprint
import re

# For formatters
import cgi  # cgi.escape
import urllib  # for urllib.encode
import urlparse  # for urljoin


class Error(Exception):
  """Base class for all exceptions in this module.

  Thus you can "except jsontemplate.Error: to catch all exceptions thrown by
  this module.
  """

  def __str__(self):
    """This helps people debug their templates.

    If a variable isn't defined, then some context is shown in the traceback.
    TODO: Attach context for other errors.
    """
    if hasattr(self, 'near'):
      return '%s\n\nNear: %s' % (self.args[0], pprint.pformat(self.near))
    else:
      return self.args[0]


class CompilationError(Error):
  """Base class for errors that happen during the compilation stage."""


class EvaluationError(Error):
  """Base class for errors that happen when expanding the template.

  This class of errors generally involve the data dictionary or the execution of
  the formatters.
  """
  def __init__(self, msg, original_exception=None):
    Error.__init__(self, msg)
    self.original_exception = original_exception


class BadFormatter(CompilationError):
  """A bad formatter was specified, e.g. {variable|BAD}"""

class BadPredicate(CompilationError):
  """A bad predicate was specified, e.g. {.BAD?}"""

class MissingFormatter(CompilationError):
  """
  Raised when formatters are required, and a variable is missing a formatter.
  """

class ConfigurationError(CompilationError):
  """
  Raised when the Template options are invalid and it can't even be compiled.
  """

class TemplateSyntaxError(CompilationError):
  """Syntax error in the template text."""

class UndefinedVariable(EvaluationError):
  """The template contains a variable not defined by the data dictionary."""


_SECTION_RE = re.compile(r'(repeated)?\s*section\s+(\S+)')

# Some formatters and predicates need to look up values in the whole context,
# rather than just the current node.  'Node functions' start with a lowercase
# letter; 'Context functions' start with any other character.
SIMPLE_FUNC, ENHANCED_FUNC = 0, 1


class FunctionRegistry(object):
  """Abstract class for looking up formatters or predicates at compile time."""

  def Lookup(self, user_str):
    """Lookup a function.

    Args:
      user_str: A raw string from the user, which may include uninterpreted
        arguments.  For example, 'pluralize person people' or 'test? admin'

    Returns:
      A 2-tuple of (function, args)
        function: Callable that formats data as a string
        args: Extra arguments to be passed to the function at expansion time
          Should be None to pass NO arguments, since it can pass a 0-tuple too.
    """
    raise NotImplementedError

  def LookupWithType(self, user_str):
    func, args = self.Lookup(user_str)
    # If users need the complexity of FunctionRegistry, then they get the
    # 3-arguments formatter signature (value, context, args)
    return func, args, ENHANCED_FUNC


def _DecideFuncType(user_str):
  """
  By default, formatters/predicates which start with a non-lowercase letter take
  contexts rather than just the cursor.
  """
  if user_str[0].islower():
    return SIMPLE_FUNC
  else:
    return ENHANCED_FUNC


class DictRegistry(FunctionRegistry):
  """Look up functions in a simple dictionary."""

  def __init__(self, func_dict):
    self.func_dict = func_dict

  def LookupWithType(self, user_str):
    return self.func_dict.get(user_str), None, _DecideFuncType(user_str)


class CallableRegistry(FunctionRegistry):
  """Look up functions in a (higher-order) function."""

  def __init__(self, func):
    self.func = func

  def LookupWithType(self, user_str):
    return self.func(user_str), None, _DecideFuncType(user_str)


class PrefixRegistry(FunctionRegistry):
  """Lookup functions with arguments.
  
  The function name is identified by a prefix.  The character after the prefix,
  usually a space, is considered the argument delimiter (similar to sed/perl's
  s/foo/bar s|foo|bar syntax).
  """

  def __init__(self, functions):
    """
    Args:
      functions: List of 2-tuples (prefix, function), e.g.
      [('pluralize', _Pluralize), ('cycle', _Cycle)]
    """
    self.functions = functions

  def Lookup(self, user_str):
    for prefix, func in self.functions:
      if user_str.startswith(prefix):
        i = len(prefix)

        # Usually a space, but could be something else
        try:
          splitchar = user_str[i]
        except IndexError:
          args = ()  # No arguments
        else:
          args = user_str.split(splitchar)[1:]

        return func, args
    return None, ()


class ChainedRegistry(FunctionRegistry):
  """Look up functions in chain of other FunctionRegistry instances."""

  def __init__(self, registries):
    self.registries = registries

  def LookupWithType(self, user_str):
    for registry in self.registries:
      func, args, func_type = registry.LookupWithType(user_str)
      if func:
        return func, args, func_type

    # Nothing found
    return None, None, SIMPLE_FUNC


class _ProgramBuilder(object):
  """
  Receives method calls from the parser, and constructs a tree of _Section()
  instances.
  """

  def __init__(self, formatters, predicates):
    """
    Args:
      formatters: See docstring for CompileTemplate
      predicates: See docstring for CompileTemplate
    """
    self.current_block = _Section()
    self.stack = [self.current_block]

    # Passing a dictionary or a function is often more convenient than making a
    # FunctionRegistry
    if isinstance(formatters, dict):
      formatters = DictRegistry(formatters)
    elif callable(formatters):
      formatters = CallableRegistry(formatters)

    # default formatters with arguments
    default_formatters = PrefixRegistry([
        ('pluralize', _Pluralize), ('cycle', _Cycle)
        ])

    # First consult user formatters, then the default formatters
    self.formatters = ChainedRegistry(
        [formatters, DictRegistry(_DEFAULT_FORMATTERS), default_formatters])

    # Same for predicates
    if isinstance(predicates, dict):
      predicates = DictRegistry(predicates)
    elif callable(predicates):
      predicates = CallableRegistry(predicates)

    self.predicates = ChainedRegistry(
        [predicates, DictRegistry(_DEFAULT_PREDICATES)])

  def Append(self, statement):
    """
    Args:
      statement: Append a literal
    """
    self.current_block.Append(statement)

  def _GetFormatter(self, format_str):
    """
    The user's formatters are consulted first, then the default formatters.
    """
    formatter, args, func_type = self.formatters.LookupWithType(format_str)
    if formatter:
      return formatter, args, func_type
    else:
      raise BadFormatter('%r is not a valid formatter' % format_str)

  def _GetPredicate(self, pred_str):
    """
    The user's predicates are consulted first, then the default predicates.
    """
    predicate, args, func_type = self.predicates.LookupWithType(pred_str)
    if predicate:
      return predicate, args, func_type
    else:
      raise BadPredicate('%r is not a valid predicate' % pred_str)

  def AppendSubstitution(self, name, formatters):
    formatters = [self._GetFormatter(f) for f in formatters]
    self.current_block.Append((_DoSubstitute, (name, formatters)))

  def _NewSection(self, func, new_block):
    self.current_block.Append((func, new_block))
    self.stack.append(new_block)
    self.current_block = new_block

  def NewSection(self, token_type, section_name):
    """For sections or repeated sections."""

    # TODO: Consider getting rid of this dispatching, and turn _Do* into methods
    if token_type == REPEATED_SECTION_TOKEN:
      new_block = _RepeatedSection(section_name)
      func = _DoRepeatedSection
    elif token_type == SECTION_TOKEN:
      new_block = _Section(section_name)
      func = _DoSection
    else:
      raise AssertionError('Invalid token type %s' % token_type)

    self._NewSection(func, new_block)

  def NewOrClause(self, pred_str):
    """
    {.or ...} Can appear inside predicate blocks or section blocks, with
    slightly different meaning.
    """
    if pred_str:
      pred = self._GetPredicate(pred_str)
    else:
      pred = None
    self.current_block.NewOrClause(pred)

  def AlternatesWith(self):
    self.current_block.AlternatesWith()

  def NewPredicateSection(self, pred_str):
    """For chains of predicate clauses."""
    pred = self._GetPredicate(pred_str)
    block = _PredicateSection()
    block.NewOrClause(pred)

    self._NewSection(_DoPredicates, block)

  def EndSection(self):
    self.stack.pop()
    self.current_block = self.stack[-1]

  def Root(self):
    # It's assumed that we call this at the end of the program
    return self.current_block


class _AbstractSection(object):

  def __init__(self):
    # Pairs of func, args, or a literal string
    self.current_clause = []

  def Append(self, statement):
    """Append a statement to this block."""
    self.current_clause.append(statement)

  def AlternatesWith(self):
    raise TemplateSyntaxError(
        '{.alternates with} can only appear with in {.repeated section ...}')

  def NewOrClause(self):
    raise NotImplementedError


class _Section(_AbstractSection):
  """Represents a (repeated) section."""

  def __init__(self, section_name=None):
    """
    Args:
      section_name: name given as an argument to the section
      token_type: The token type that created this section (e.g.
          PREDICATE_TOKEN)
    """
    _AbstractSection.__init__(self)
    self.section_name = section_name

    # Clauses is just a string and a list of statements.
    self.statements = {'default': self.current_clause}

  def __repr__(self):
    return '<Section %s>' % self.section_name

  def Statements(self, clause='default'):
    return self.statements.get(clause, [])

  def NewOrClause(self, pred):
    if pred:
      raise TemplateSyntaxError(
          '{.or} clause only takes a predicate inside predicate blocks')
    self.current_clause = []
    self.statements['or'] = self.current_clause


class _RepeatedSection(_Section):
  """Repeated section is like section, but it supports {.alternates with}"""

  def AlternatesWith(self):
    self.current_clause = []
    self.statements['alternates with'] = self.current_clause


class _PredicateSection(_AbstractSection):
  """Represents a sequence of predicate clauses."""

  def __init__(self):
    _AbstractSection.__init__(self)
    # List of func, statements
    self.clauses = []

  def NewOrClause(self, pred):
    # {.or} always executes if reached
    pred = pred or (lambda x: True, None, SIMPLE_FUNC)  # 3-tuple
    self.current_clause = []
    self.clauses.append((pred, self.current_clause))


class _Frame(object):
  """A stack frame."""

  def __init__(self, context, index=-1):
    # Public attributes
    self.context = context
    self.index = index   # An iteration index.  -1 means we're NOT iterating.

  def __str__(self):
    return 'Frame %s (%s)' % (self.context, self.index)


class _ScopedContext(object):
  """Allows scoped lookup of variables.

  If the variable isn't in the current context, then we search up the stack.
  """

  def __init__(self, context, undefined_str):
    """
    Args:
      context: The root context
      undefined_str: See Template() constructor.
    """
    self.stack = [_Frame(context)]
    self.undefined_str = undefined_str

  def PushSection(self, name):
    """Given a section name, push it on the top of the stack.

    Returns:
      The new section, or None if there is no such section.
    """
    if name == '@':
      new_context = self.stack[-1].context
    else:
      new_context = self.stack[-1].context.get(name)
    self.stack.append(_Frame(new_context))
    return new_context

  def Pop(self):
    self.stack.pop()

  def Next(self):
    """Advance to the next item in a repeated section.

    Raises:
      StopIteration if there are no more elements
    """
    stacktop = self.stack[-1]

    # Now we're iterating -- push a new mutable object onto the stack
    if stacktop.index == -1:
      stacktop = _Frame(None, index=0)
      self.stack.append(stacktop)

    context_array = self.stack[-2].context

    if stacktop.index == len(context_array):
      self.stack.pop()
      raise StopIteration

    stacktop.context = context_array[stacktop.index]
    stacktop.index += 1

    return True  # OK, we mutated the stack

  def _Undefined(self, name):
    if self.undefined_str is None:
      raise UndefinedVariable('%r is not defined' % name)
    else:
      return self.undefined_str

  def _LookUpStack(self, name):
    """Look up the stack for the given name."""
    i = len(self.stack) - 1
    while 1:
      frame = self.stack[i]
      if name == '@index':
        if frame.index != -1:  # -1 is undefined
          return frame.index  # @index is 1-based
      else:
        context = frame.context
        if hasattr(context, 'get'):  # Can't look up names in a list or atom
          try:
            return context[name]
          except KeyError:
            pass

      i -= 1  # Next frame
      if i <= -1:  # Couldn't find it anywhere
        return self._Undefined(name)

  def Lookup(self, name):
    """Get the value associated with a name in the current context.

    The current context could be an dictionary in a list, or a dictionary
    outside a list.

    Args:
      name: name to lookup, e.g. 'foo' or 'foo.bar.baz'

    Returns:
      The value, or self.undefined_str

    Raises:
      UndefinedVariable if self.undefined_str is not set
    """
    if name == '@':
      return self.stack[-1].context

    parts = name.split('.')
    value = self._LookUpStack(parts[0])

    # Now do simple lookups of the rest of the parts
    for part in parts[1:]:
      try:
        value = value[part]
      except (KeyError, TypeError):  # TypeError for non-dictionaries
        return self._Undefined(part)

    return value


def _ToString(x):
  # Some cross-language values for primitives
  if x is None:
    return 'null'
  if isinstance(x, basestring):
    return x
  return pprint.pformat(x)


def _HtmlAttrValue(x):
  return cgi.escape(x, quote=True)


def _AbsUrl(relative_url, context, unused_args):
  """Returns an absolute URL, given the current node as a relative URL.

  Assumes that the context has a value named 'base-url'.  This is a little like
  the HTML <base> tag, but implemented with HTML generation.

  Raises:
    UndefinedVariable if 'base-url' doesn't exist
  """
  # urljoin is flexible about trailing/leading slashes -- it will add or de-dupe
  # them
  return urlparse.urljoin(context.Lookup('base-url'), relative_url)


# See http://google-ctemplate.googlecode.com/svn/trunk/doc/howto.html for more
# escape types.
#
# Also, we might want to take a look at Django filters.
#
# This is a *public* constant, so that callers can use it construct their own
# formatter lookup dictionaries, and pass them in to Template.
_DEFAULT_FORMATTERS = {
    'html': cgi.escape,

    # The 'htmltag' name is deprecated.  The html-attr-value name is preferred
    # because it can be read with "as":
    #   {url|html-attr-value} means:
    #   "substitute 'url' as an HTML attribute value"
    'html-attr-value': _HtmlAttrValue,
    'htmltag': _HtmlAttrValue,

    'raw': lambda x: x,
    # Used for the length of a list.  Can be used for the size of a dictionary
    # too, though I haven't run into that use case.
    'size': lambda value: str(len(value)),

    # The argument is a dictionary, and we get a a=1&b=2 string back.
    'url-params': urllib.urlencode,

    # The argument is an atom, and it takes 'Search query?' -> 'Search+query%3F'
    'url-param-value': urllib.quote_plus,  # param is an atom

    # The default formatter, when no other default is specifier.  For debugging,
    # this could be lambda x: json.dumps(x, indent=2), but here we want to be
    # compatible to Python 2.4.
    'str': _ToString,

    # Just show a plain URL on an HTML page (without anchor text).
    'plain-url': lambda x: '<a href="%s">%s</a>' % (
        cgi.escape(x, quote=True), cgi.escape(x)),

    # A context formatter
    'AbsUrl': _AbsUrl,

    # Placeholders for "standard names".  We're not including them by default
    # since they require additional dependencies.  We can provide a part of the
    # "lookup chain" in formatters.py for people people want the dependency.

    # 'json' formats arbitrary data dictionary nodes as JSON strings.  'json'
    # and 'js-string' are identical (since a JavaScript string *is* JSON).  The
    # latter is meant to be serve as extra documentation when you want a string
    # argument only, which is a common case.
    'json': None,
    'js-string': None,
    }


def _Pluralize(value, unused_context, args):
  """Formatter to pluralize words."""

  if len(args) == 0:
    s, p = '', 's'
  elif len(args) == 1:
    s, p = '', args[0]
  elif len(args) == 2:
    s, p = args
  else:
    # Should have been checked at compile time
    raise AssertionError

  if value > 1:
    return p
  else:
    return s


def _Cycle(value, unused_context, args):
  """Cycle between various values on consecutive integers."""
  # @index starts from 1, so used 1-based indexing
  return args[(value - 1) % len(args)]


def _IsDebugMode(unused_value, context, unused_args):
  try:
    return bool(context.Lookup('debug'))
  except UndefinedVariable:
    return False


_DEFAULT_PREDICATES = {
    'singular?': lambda x: x == 1,
    'plural?': lambda x: x > 1,
    'Debug?': _IsDebugMode,
    }


def SplitMeta(meta):
  """Split and validate metacharacters.

  Example: '{}' -> ('{', '}')

  This is public so the syntax highlighter and other tools can use it.
  """
  n = len(meta)
  if n % 2 == 1:
    raise ConfigurationError(
        '%r has an odd number of metacharacters' % meta)
  return meta[:n/2], meta[n/2:]


_token_re_cache = {}

def MakeTokenRegex(meta_left, meta_right):
  """Return a (compiled) regular expression for tokenization.

  Args:
    meta_left, meta_right: e.g. '{' and '}'

  - The regular expressions are memoized.
  - This function is public so the syntax highlighter can use it.
  """
  key = meta_left, meta_right
  if key not in _token_re_cache:
    # - Need () grouping for re.split
    # - For simplicity, we allow all characters except newlines inside
    #   metacharacters ({} / [])
    _token_re_cache[key] = re.compile(
        r'(' +
        re.escape(meta_left) +
        r'.+?' +
        re.escape(meta_right) +
        r')')
  return _token_re_cache[key]


# Examples:

( LITERAL_TOKEN,  # "Hi"
  SUBSTITUTION_TOKEN,  # {var|html}
  SECTION_TOKEN,  # {.section name}
  REPEATED_SECTION_TOKEN,  # {.repeated section name}
  PREDICATE_TOKEN,  # {.predicate?}
  ALTERNATES_TOKEN,  # {.or}
  OR_TOKEN,  # {.or}
  END_TOKEN,  # {.end}
  ) = range(8)


def _MatchDirective(token):
  """Helper function for matching certain directives."""

  if token.startswith('.'):
    token = token[1:]
  else:
    return None, None  # Must start with .

  if token == 'alternates with':
    return ALTERNATES_TOKEN, token

  if token.startswith('or'):
    if token.strip() == 'or':
      return OR_TOKEN, None
    else:
      pred_str = token[2:].strip()
      return OR_TOKEN, pred_str

  if token == 'end':
    return END_TOKEN, None

  match = _SECTION_RE.match(token)
  if match:
    repeated, section_name = match.groups()
    if repeated:
      return REPEATED_SECTION_TOKEN, section_name
    else:
      return SECTION_TOKEN, section_name

  # {.if plural?} and {.plural?} are synonyms.  The ".if" will read better for
  # expressions, for people who like that kind of dirty thing...
  if token.startswith('if '):
    return PREDICATE_TOKEN, token[3:].strip()
  if token.endswith('?'):
    return PREDICATE_TOKEN, token

  return None, None  # no match


def _Tokenize(template_str, meta_left, meta_right):
  """Yields tokens, which are 2-tuples (TOKEN_TYPE, token_string)."""

  trimlen = len(meta_left)

  token_re = MakeTokenRegex(meta_left, meta_right)

  for line in template_str.splitlines(True):  # retain newlines
    tokens = token_re.split(line)

    # Check for a special case first.  If a comment or "block" directive is on a
    # line by itself (with only space surrounding it), then the space is
    # omitted.  For simplicity, we don't handle the case where we have 2
    # directives, say '{.end} # {#comment}' on a line.

    if len(tokens) == 3:
      # ''.isspace() == False, so work around that
      if (tokens[0].isspace() or not tokens[0]) and \
         (tokens[2].isspace() or not tokens[2]):
        token = tokens[1][trimlen : -trimlen]

        if token.startswith('#'):
          continue  # The whole line is omitted

        token_type, token = _MatchDirective(token)
        if token_type is not None:
          yield token_type, token  # Only yield the token, not space
          continue

    # The line isn't special; process it normally.

    for i, token in enumerate(tokens):
      if i % 2 == 0:
        yield LITERAL_TOKEN, token

      else:  # It's a "directive" in metachracters

        assert token.startswith(meta_left), repr(token)
        assert token.endswith(meta_right), repr(token)
        token = token[trimlen : -trimlen]

        # It's a comment
        if token.startswith('#'):
          continue

        if token.startswith('.'):

          literal = {
              '.meta-left': meta_left,
              '.meta-right': meta_right,
              '.space': ' ',
              '.tab': '\t',
              '.newline': '\n',
              }.get(token)

          if literal is not None:
            yield LITERAL_TOKEN, literal
            continue

          token_type, token = _MatchDirective(token)
          if token_type is not None:
            yield token_type, token

        else:  # Now we know the directive is a substitution.
          yield SUBSTITUTION_TOKEN, token


def CompileTemplate(
    template_str, builder=None, meta='{}', format_char='|',
    more_formatters=lambda x: None, more_predicates=lambda x: None,
    default_formatter='str'):
  """Compile the template string, calling methods on the 'program builder'.

  Args:
    template_str: The template string.  It should not have any compilation
        options in the header -- those are parsed by FromString/FromFile

    builder: The interface of _ProgramBuilder isn't fixed.  Use at your own
        risk.

    meta: The metacharacters to use, e.g. '{}', '[]'.

    more_formatters:
        Something that can map format strings to formatter functions.  One of:
          - A plain dictionary of names -> functions  e.g. {'html': cgi.escape}
          - A higher-order function which takes format strings and returns
            formatter functions.  Useful for when formatters have parsed
            arguments.
          - A FunctionRegistry instance for the most control.  This allows
            formatters which takes contexts as well.

    more_predicates:
        Like more_formatters, but for predicates.

    default_formatter: The formatter to use for substitutions that are missing a
        formatter.  The 'str' formatter the "default default" -- it just tries
        to convert the context value to a string in some unspecified manner.

  Returns:
    The compiled program (obtained from the builder)

  Raises:
    The various subclasses of CompilationError.  For example, if
    default_formatter=None, and a variable is missing a formatter, then
    MissingFormatter is raised.

  This function is public so it can be used by other tools, e.g. a syntax
  checking tool run before submitting a template to source control.
  """
  builder = builder or _ProgramBuilder(more_formatters, more_predicates)
  meta_left, meta_right = SplitMeta(meta)

  # : is meant to look like Python 3000 formatting {foo:.3f}.  According to
  # PEP 3101, that's also what .NET uses.
  # | is more readable, but, more importantly, reminiscent of pipes, which is
  # useful for multiple formatters, e.g. {name|js-string|html}
  if format_char not in (':', '|'):
    raise ConfigurationError(
        'Only format characters : and | are accepted (got %r)' % format_char)

  # If we go to -1, then we got too many {end}.  If end at 1, then we're missing
  # an {end}.
  balance_counter = 0

  for token_type, token in _Tokenize(template_str, meta_left, meta_right):

    if token_type == LITERAL_TOKEN:
      if token:
        builder.Append(token)
      continue

    if token_type in (SECTION_TOKEN, REPEATED_SECTION_TOKEN):
      builder.NewSection(token_type, token)
      balance_counter += 1
      continue

    if token_type == PREDICATE_TOKEN:
      # Everything of the form {.predicate?} starts a new predicate section
      block_made = builder.NewPredicateSection(token)
      balance_counter += 1
      continue

    if token_type == OR_TOKEN:
      builder.NewOrClause(token)
      continue

    if token_type == ALTERNATES_TOKEN:
      builder.AlternatesWith()
      continue

    if token_type == END_TOKEN:
      balance_counter -= 1
      if balance_counter < 0:
        # TODO: Show some context for errors
        raise TemplateSyntaxError(
            'Got too many %send%s statements.  You may have mistyped an '
            "earlier 'section' or 'repeated section' directive."
            % (meta_left, meta_right))
      builder.EndSection()
      continue

    if token_type == SUBSTITUTION_TOKEN:
      parts = token.split(format_char)
      if len(parts) == 1:
        if default_formatter is None:
          raise MissingFormatter('This template requires explicit formatters.')
        # If no formatter is specified, the default is the 'str' formatter,
        # which the user can define however they desire.
        name = token
        formatters = [default_formatter]
      else:
        name = parts[0]
        formatters = parts[1:]

      builder.AppendSubstitution(name, formatters)

  if balance_counter != 0:
    raise TemplateSyntaxError('Got too few %send%s statements' %
        (meta_left, meta_right))

  return builder.Root()


_OPTION_RE = re.compile(r'^([a-zA-Z\-]+):\s*(.*)')
# TODO: whitespace mode, etc.
_OPTION_NAMES = ['meta', 'format-char', 'default-formatter', 'undefined-str']


def FromString(s, more_formatters=lambda x: None, _constructor=None):
  """Like FromFile, but takes a string."""

  f = StringIO.StringIO(s)
  return FromFile(f, more_formatters=more_formatters, _constructor=_constructor)


def FromFile(f, more_formatters=lambda x: None, _constructor=None):
  """Parse a template from a file, using a simple file format.

  This is useful when you want to include template options in a data file,
  rather than in the source code.

  The format is similar to HTTP or E-mail headers.  The first lines of the file
  can specify template options, such as the metacharacters to use.  One blank
  line must separate the options from the template body.

  Example:

    default-formatter: none
    meta: {{}}
    format-char: :
    <blank line required>
    Template goes here: {{variable:html}}

  Args:
    f: A file handle to read from.  Caller is responsible for opening and
    closing it.
  """
  _constructor = _constructor or Template

  options = {}

  # Parse lines until the first one that doesn't look like an option
  while 1:
    line = f.readline()
    match = _OPTION_RE.match(line)
    if match:
      name, value = match.group(1), match.group(2)

      # Accept something like 'Default-Formatter: raw'.  This syntax is like
      # HTTP/E-mail headers.
      name = name.lower()

      if name in _OPTION_NAMES:
        name = name.replace('-', '_')
        value = value.strip()
        if name == 'default_formatter' and value.lower() == 'none':
          value = None
        options[name] = value
      else:
        break
    else:
      break

  if options:
    if line.strip():
      raise CompilationError(
          'Must be one blank line between template options and body (got %r)'
          % line)
    body = f.read()
  else:
    # There were no options, so no blank line is necessary.
    body = line + f.read()

  return _constructor(body, more_formatters=more_formatters, **options)


class Template(object):
  """Represents a compiled template.

  Like many template systems, the template string is compiled into a program,
  and then it can be expanded any number of times.  For example, in a web app,
  you can compile the templates once at server startup, and use the expand()
  method at request handling time.  expand() uses the compiled representation.

  There are various options for controlling parsing -- see CompileTemplate.
  Don't go crazy with metacharacters.  {}, [], {{}} or <> should cover nearly
  any circumstance, e.g. generating HTML, CSS XML, JavaScript, C programs, text
  files, etc.
  """

  def __init__(self, template_str, builder=None, undefined_str=None,
               **compile_options):
    """
    Args:
      template_str: The template string.
      undefined_str: A string to appear in the output when a variable to be
          substituted is missing.  If None, UndefinedVariable is raised.
          (Note: This is not really a compilation option, because affects
          template expansion rather than compilation.  Nonetheless we make it a
          constructor argument rather than an .expand() argument for
          simplicity.)

    It also accepts all the compile options that CompileTemplate does.
    """
    self._program = CompileTemplate(
        template_str, builder=builder, **compile_options)
    self.undefined_str = undefined_str

  #
  # Public API
  #

  def render(self, data_dict, callback):
    """Low level method to expands the template piece by piece.

    Args:
      data_dict: The JSON data dictionary.
      callback: A callback which should be called with each expanded token.

    Example: You can pass 'f.write' as the callback to write directly to a file
    handle.
    """
    context = _ScopedContext(data_dict, self.undefined_str)
    _Execute(self._program.Statements(), context, callback)

  def expand(self, *args, **kwargs):
    """Expands the template with the given data dictionary, returning a string.

    This is a small wrapper around render(), and is the most convenient
    interface.

    Args:
      The JSON data dictionary.  Like the builtin dict() constructor, it can
      take a single dictionary as a positional argument, or arbitrary keyword
      arguments.

    Returns:
      The return value could be a str() or unicode() instance, depending on the
      the type of the template string passed in, and what the types the strings
      in the dictionary are.
    """
    if args:
      if len(args) == 1:
        data_dict = args[0]
      else:
        raise TypeError(
            'expand() only takes 1 positional argument (got %s)' % args)
    else:
      data_dict = kwargs

    tokens = []
    self.render(data_dict, tokens.append)
    return ''.join(tokens)

  def tokenstream(self, data_dict):
    """Yields a list of tokens resulting from expansion.

    This may be useful for WSGI apps.  NOTE: In the current implementation, the
    entire expanded template must be stored memory.

    NOTE: This is a generator, but JavaScript doesn't have generators.
    """
    tokens = []
    self.render(data_dict, tokens.append)
    for token in tokens:
      yield token


def _DoRepeatedSection(args, context, callback):
  """{repeated section foo}"""

  block = args

  items = context.PushSection(block.section_name)
  # TODO: if 'items' is a dictionary, allow @name and @value.

  if items:
    if not isinstance(items, list):
      raise EvaluationError('Expected a list; got %s' % type(items))

    last_index = len(items) - 1
    statements = block.Statements()
    alt_statements = block.Statements('alternates with')
    try:
      i = 0
      while True:
        context.Next()
        # Execute the statements in the block for every item in the list.
        # Execute the alternate block on every iteration except the last.  Each
        # item could be an atom (string, integer, etc.) or a dictionary.
        _Execute(statements, context, callback)
        if i != last_index:
          _Execute(alt_statements, context, callback)
        i += 1
    except StopIteration:
      pass

  else:
    _Execute(block.Statements('or'), context, callback)

  context.Pop()


def _DoSection(args, context, callback):
  """{section foo}"""

  block = args
  # If a section present and "true", push the dictionary onto the stack as the
  # new context, and show it
  if context.PushSection(block.section_name):
    _Execute(block.Statements(), context, callback)
    context.Pop()
  else:  # missing or "false" -- show the {.or} section
    context.Pop()
    _Execute(block.Statements('or'), context, callback)


def _DoPredicates(args, context, callback):
  """{.predicate?}

  Here we execute the first clause that evaluates to true, and then stop.
  """
  block = args
  value = context.Lookup('@')
  for (predicate, args, func_type), statements in block.clauses:
    if func_type == ENHANCED_FUNC:
      do_clause = predicate(value, context, args)
    else:
      do_clause = predicate(value)

    if do_clause:
      _Execute(statements, context, callback)
      break


def _DoSubstitute(args, context, callback):
  """Variable substitution, e.g. {foo}"""

  name, formatters = args

  # So we can have {.section is_new}new since {@}{.end}.  Hopefully this idiom
  # is OK.
  if name == '@':
    value = context.Lookup('@')
  else:
    try:
      value = context.Lookup(name)
    except TypeError, e:
      raise EvaluationError(
          'Error evaluating %r in context %r: %r' % (name, context, e))

  for func, args, func_type in formatters:
    try:
      if func_type == ENHANCED_FUNC:
        value = func(value, context, args)
      else:
        value = func(value)
    except KeyboardInterrupt:
      raise
    except Exception, e:
      raise EvaluationError(
          'Formatting value %r with formatter %s raised exception: %r' %
          (value, formatters, e), original_exception=e)

  # TODO: Require a string/unicode instance here?
  if value is None:
    raise EvaluationError('Evaluating %r gave None value' % name)
  callback(value)


def _Execute(statements, context, callback):
  """Execute a bunch of template statements in a ScopedContext.

  Args:
    callback: Strings are "written" to this callback function.

  This is called in a mutually recursive fashion.
  """

  for i, statement in enumerate(statements):
    if isinstance(statement, basestring):
      callback(statement)
    else:
      # In the case of a substitution, args is a pair (name, formatters).
      # In the case of a section, it's a _Section instance.
      try:
        func, args = statement
        func(args, context, callback)
      except UndefinedVariable, e:
        # Show context for statements
        start = max(0, i-3)
        end = i+3
        e.near = statements[start:end]
        raise


def expand(template_str, dictionary, **kwargs):
  """Free function to expands a template string with a data dictionary.

  This is useful for cases where you don't care about saving the result of
  compilation (similar to re.match('.*', s) vs DOT_STAR.match(s))
  """
  t = Template(template_str, **kwargs)
  return t.expand(dictionary)
