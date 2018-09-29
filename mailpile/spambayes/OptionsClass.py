"""OptionsClass

Classes:
    Option - Holds information about an option
    OptionsClass - A collection of options

Abstract:

This module is used to manage "options" managed in user editable files.
This is the implementation of the Options.options globally shared options
object for the SpamBayes project, but is also able to be used to manage
other options required by each application.

The Option class holds information about an option - the name of the
option, a nice name (to display), documentation, default value,
possible values (a tuple or a regex pattern), whether multiple values
are allowed, and whether the option should be reset when restoring to
defaults (options like server names should *not* be).

The OptionsClass class provides facility for a collection of Options.
It is expected that manipulation of the options will be carried out
via an instance of this class.

Experimental or deprecated options are prefixed with 'x-', borrowing the
practice from RFC-822 mail.  If the user sets an option like:

    [Tokenizer]
    x-transmogrify: True

and an 'x-transmogrify' or 'transmogrify' option exists, it is set silently
to the value given by the user.  If the user sets an option like:

    [Tokenizer]
    transmogrify: True

and no 'transmogrify' option exists, but an 'x-transmogrify' option does,
the latter is set to the value given by the users and a deprecation message
is printed to standard error.

To Do:
 o Stop allowing invalid options in configuration files
 o Find a regex expert to come up with *good* patterns for domains,
   email addresses, and so forth.
 o str(Option) should really call Option.unconvert since this is what
   it does.  Try putting that in and running all the tests.
 o [See also the __issues__ string.]
 o Suggestions?

"""

# This module is part of the spambayes project, which is Copyright 2002-2007
# The Python Software Foundation and is covered by the Python Software
# Foundation license.

__credits__ = "All the Spambayes folk."
# blame for the new format: Tony Meyer <ta-meyer@ihug.co.nz>

__issues__ = """Things that should be considered further and by
other people:

We are very generous in checking validity when multiple values are
allowed and the check is a regex (rather than a tuple).  Any sequence
that does not match the regex may be used to delimit the values.
For example, if the regex was simply r"[\d]*" then these would all
be considered valid:
"123a234" -> 123, 234
"123abced234" -> 123, 234
"123XST234xas" -> 123, 234
"123 234" -> 123, 234
"123~!@$%^&@234!" -> 123, 234

If this is a problem, my recommendation would be to change the
multiple_values_allowed attribute from a boolean to a regex/None
i.e. if multiple is None, then only one value is allowed.  Otherwise
multiple is used in a re.split() to separate the input.
"""

import sys
import os
import shutil
from tempfile import TemporaryFile

try:
    import cStringIO as StringIO
except ImportError:
    import StringIO

import re
import types
import locale
from textwrap import wrap

__all__ = ['OptionsClass',
           'HEADER_NAME', 'HEADER_VALUE',
           'INTEGER', 'REAL', 'BOOLEAN',
           'SERVER', 'PORT', 'EMAIL_ADDRESS',
           'PATH', 'VARIABLE_PATH', 'FILE', 'FILE_WITH_PATH',
           'IMAP_FOLDER', 'IMAP_ASTRING',
           'RESTORE', 'DO_NOT_RESTORE', 'IP_LIST',
           'OCRAD_CHARSET',
          ]

MultiContainerTypes = (types.TupleType, types.ListType)

class Option(object):
    def __init__(self, name, nice_name="", default=None,
                 help_text="", allowed=None, restore=True):
        self.name = name
        self.nice_name = nice_name
        self.default_value = default
        self.explanation_text = help_text
        self.allowed_values = allowed
        self.restore = restore
        self.delimiter = None
        # start with default value
        self.set(default)

    def display_name(self):
        '''A name for the option suitable for display to a user.'''
        return self.nice_name
    def default(self):
        '''The default value for the option.'''
        return self.default_value
    def doc(self):
        '''Documentation for the option.'''
        return self.explanation_text
    def valid_input(self):
        '''Valid values for the option.'''
        return self.allowed_values
    def no_restore(self):
        '''Do not restore this option when restoring to defaults.'''
        return not self.restore
    def set(self, val):
        '''Set option to value.'''
        self.value = val
    def get(self):
        '''Get option value.'''
        return self.value
    def multiple_values_allowed(self):
        '''Multiple values are allowed for this option.'''
        return type(self.default_value) in MultiContainerTypes

    def is_valid(self, value):
        '''Check if this is a valid value for this option.'''
        if self.allowed_values is None:
            return False

        if self.multiple_values_allowed():
            return self.is_valid_multiple(value)
        else:
            return self.is_valid_single(value)

    def is_valid_multiple(self, value):
        '''Return True iff value is a valid value for this option.
        Use if multiple values are allowed.'''
        if type(value) in MultiContainerTypes:
            for val in value:
                if not self.is_valid_single(val):
                    return False
            return True
        return self.is_valid_single(value)

    def is_valid_single(self, value):
        '''Return True iff value is a valid value for this option.
        Use when multiple values are not allowed.'''
        if type(self.allowed_values) == types.TupleType:
            if value in self.allowed_values:
                return True
            else:
                return False
        else:
            # special handling for booleans, thanks to Python 2.2
            if self.is_boolean and (value == True or value == False):
                return True
            if type(value) != type(self.value) and \
               type(self.value) not in MultiContainerTypes:
                # This is very strict!  If the value is meant to be
                # a real number and an integer is passed in, it will fail.
                # (So pass 1. instead of 1, for example)
                return False
            if value == "":
                # A blank string is always ok.
                return True
            avals = self._split_values(value)
            # in this case, allowed_values must be a regex, and
            # _split_values must match once and only once
            if len(avals) == 1:
                return True
            else:
                # either no match or too many matches
                return False

    def _split_values(self, value):
        # do the regex mojo here
        if not self.allowed_values:
            return ('',)
        try:
            r = re.compile(self.allowed_values)
        except:
            print >> sys.stderr, self.allowed_values
            raise
        s = str(value)
        i = 0
        vals = []
        while True:
            m = r.search(s[i:])
            if m is None:
                break
            vals.append(m.group())
            delimiter = s[i:i + m.start()]
            if self.delimiter is None and delimiter != "":
                self.delimiter = delimiter
            i += m.end()
        return tuple(vals)

    def as_nice_string(self, section=None):
        '''Summarise the option in a user-readable format.'''
        if section is None:
            strval = ""
        else:
            strval = "[%s] " % (section)
        strval += "%s - \"%s\"\nDefault: %s\nDo not restore: %s\n" \
                 % (self.name, self.display_name(),
                    str(self.default()), str(self.no_restore()))
        strval += "Valid values: %s\nMultiple values allowed: %s\n" \
                  % (str(self.valid_input()),
                     str(self.multiple_values_allowed()))
        strval += "\"%s\"\n\n" % (str(self.doc()))
        return strval

    def as_documentation_string(self, section=None):
        '''Summarise the option in a format suitable for unmodified
        insertion in HTML documentation.'''
        strval = ["<tr>"]
        if section is not None:
            strval.append("\t<td>[%s]</td>" % (section,))
        strval.append("\t<td>%s</td>" % (self.name,))
        strval.append("\t<td>%s</td>" % \
                      ", ".join([str(s) for s in self.valid_input()]))
        default = self.default()
        if isinstance(default, types.TupleType):
            default = ", ".join([str(s) for s in default])
        else:
            default = str(default)
        strval.append("\t<td>%s</td>" % (default,))
        strval.append("\t<td><strong>%s</strong>: %s</td>" \
                      % (self.display_name(), self.doc()))
        strval.append("</tr>\n")
        return "\n".join(strval)

    def write_config(self, file):
        '''Output value in configuration file format.'''
        file.write(self.name)
        file.write(': ')
        file.write(self.unconvert())
        file.write('\n')

    def convert(self, value):
        '''Convert value from a string to the appropriate type.'''
        svt = type(self.value)
        if svt == type(value):
            # already the correct type
            return value
        if type(self.allowed_values) == types.TupleType and \
           value in self.allowed_values:
            # already correct type
            return value
        if self.is_boolean():
            if str(value) == "True" or value == 1:
                return True
            elif str(value) == "False" or value == 0:
                return False
            raise TypeError, self.name + " must be True or False"
        if self.multiple_values_allowed():
            # This will fall apart if the allowed_value is a tuple,
            # but not a homogenous one...
            if isinstance(self.allowed_values, types.StringTypes):
                vals = list(self._split_values(value))
            else:
                if isinstance(value, types.TupleType):
                    vals = list(value)
                else:
                    vals = value.split()
            if len(self.default_value) > 0:
                to_type = type(self.default_value[0])
            else:
                to_type = types.StringType
            for i in range(0, len(vals)):
                vals[i] = self._convert(vals[i], to_type)
            return tuple(vals)
        else:
            return self._convert(value, svt)
        raise TypeError, self.name + " has an invalid type."

    def _convert(self, value, to_type):
        '''Convert an int, float or string to the specified type.'''
        if to_type == type(value):
            # already the correct type
            return value
        if to_type == types.IntType:
            return locale.atoi(value)
        if to_type == types.FloatType:
            return locale.atof(value)
        if to_type in types.StringTypes:
            return str(value)
        raise TypeError, "Invalid type."

    def unconvert(self):
        '''Convert value from the appropriate type to a string.'''
        if type(self.value) in types.StringTypes:
            # nothing to do
            return self.value
        if self.is_boolean():
            # A wee bit extra for Python 2.2
            if self.value == True:
                return "True"
            else:
                return "False"
        if type(self.value) == types.TupleType:
            if len(self.value) == 0:
                return ""
            if len(self.value) == 1:
                v = self.value[0]
                if type(v) == types.FloatType:
                    return locale.str(self.value[0])
                return str(v)
            # We need to separate out the items
            strval = ""
            # We use a character that is invalid as the separator
            # so that it will reparse correctly.  We could try all
            # characters, but we make do with this set of commonly
            # used ones - note that the first one that works will
            # be used.  Perhaps a nicer solution than this would be
            # to specifiy a valid delimiter for all options that
            # can have multiple values.  Note that we have None at
            # the end so that this will crash and die if none of
            # the separators works <wink>.
            if self.delimiter is None:
                if type(self.allowed_values) == types.TupleType:
                    self.delimiter = ' '
                else:
                    v0 = self.value[0]
                    v1 = self.value[1]
                    for sep in [' ', ',', ':', ';', '/', '\\', None]:
                        # we know at this point that len(self.value) is at
                        # least two, because len==0 and len==1 were dealt
                        # with as special cases
                        test_str = str(v0) + sep + str(v1)
                        test_tuple = self._split_values(test_str)
                        if test_tuple[0] == str(v0) and \
                           test_tuple[1] == str(v1) and \
                           len(test_tuple) == 2:
                            break
                    # cache this so we don't always need to do the above
                    self.delimiter = sep
            for v in self.value:
                if type(v) == types.FloatType:
                    v = locale.str(v)
                else:
                    v = str(v)
                strval += v + self.delimiter
            strval = strval[:-len(self.delimiter)] # trailing seperator
        else:
            # Otherwise, we just hope str() will do the job
            strval = str(self.value)
        return strval

    def is_boolean(self):
        '''Return True iff the option is a boolean value.'''
        # This is necessary because of the Python 2.2 True=1, False=0
        # cheat.  The valid values are returned as 0 and 1, even if
        # they are actually False and True - but 0 and 1 are not
        # considered valid input (and 0 and 1 don't look as nice)
        # So, just for the 2.2 people, we have this helper function
        try:
            if type(self.allowed_values) == types.TupleType and \
               len(self.allowed_values) > 0 and \
               type(self.allowed_values[0]) == types.BooleanType:
                return True
            return False
        except AttributeError:
            # If the user has Python 2.2 and an option has valid values
            # of (0, 1) - i.e. integers, then this function will return
            # the wrong value.  I don't know what to do about that without
            # explicitly stating which options are boolean
            if self.allowed_values == (False, True):
                return True
            return False


class OptionsClass(object):
    def __init__(self):
        self.verbose = None
        self._options = {}
        self.restore_point = {}
        self.conversion_table = {} # set by creator if they need it.
    #
    # Regular expressions for parsing section headers and options.
    # Lifted straight from ConfigParser
    #
    SECTCRE = re.compile(
        r'\['                                 # [
        r'(?P<header>[^]]+)'                  # very permissive!
        r'\]'                                 # ]
        )
    OPTCRE = re.compile(
        r'(?P<option>[^:=\s][^:=]*)'          # very permissive!
        r'\s*(?P<vi>[:=])\s*'                 # any number of space/tab,
                                              # followed by separator
                                              # (either : or =), followed
                                              # by any # space/tab
        r'(?P<value>.*)$'                     # everything up to EOL
        )

    def update_file(self, filename):
        '''Update the specified configuration file.'''
        sectname = None
        optname = None
        out = TemporaryFile()
        if os.path.exists(filename):
            f = file(filename, "r")
        else:
            # doesn't exist, so create it - all the changed options will
            # be added to it
            if self.verbose:
                print >> sys.stderr, "Creating new configuration file",
                print >> sys.stderr, filename
            f = file(filename, "w")
            f.close()
            f = file(filename, "r")
        written = []
        vi = ": " # default; uses the one from the file where possible
        while True:
            line = f.readline()
            if not line:
                break
            # comment or blank line?
            if line.strip() == '' or line[0] in '#;':
                out.write(line)
                continue
            if line.split(None, 1)[0].lower() == 'rem' and line[0] in "rR":
                # no leading whitespace
                out.write(line)
                continue
            # continuation line?
            if line[0].isspace() and sectname is not None and optname:
                continue
            # a section header or option header?
            else:
                # is it a section header?
                mo = self.SECTCRE.match(line)
                if mo:
                    # Add any missing from the previous section
                    if sectname is not None:
                        self._add_missing(out, written, sectname, vi, False)
                    sectname = mo.group('header')
                    # So sections can't start with a continuation line
                    optname = None
                    if sectname in self.sections():
                        out.write(line)
                # an option line?
                else:
                    mo = self.OPTCRE.match(line)
                    if mo:
                        optname, vi, optval = mo.group('option', 'vi', 'value')
                        if vi in ('=', ':') and ';' in optval:
                            # ';' is a comment delimiter only if it follows
                            # a spacing character
                            pos = optval.find(';')
                            if pos != -1 and optval[pos-1].isspace():
                                optval = optval[:pos]
                        optval = optval.strip()
                        # allow empty values
                        if optval == '""':
                            optval = ''
                        optname = optname.rstrip().lower()
                        if self._options.has_key((sectname, optname)):
                            out.write(optname)
                            out.write(vi)
                            newval = self.unconvert(sectname, optname)
                            out.write(newval.replace("\n", "\n\t"))
                            out.write('\n')
                            written.append((sectname, optname))
        for sect in self.sections():
            self._add_missing(out, written, sect, vi)
        f.close()
        out.flush()
        if self.verbose:
            # save a backup of the old file
            shutil.copyfile(filename, filename + ".bak")
        # copy the new file across
        f = file(filename, "w")
        out.seek(0)
        shutil.copyfileobj(out, f)
        out.close()
        f.close()

    def _add_missing(self, out, written, sect, vi, label=True):
        # add any missing ones, where the value does not equal the default
        for opt in self.options_in_section(sect):
            if not (sect, opt) in written and \
               self.get(sect, opt) != self.default(sect, opt):
                if label:
                    out.write('[')
                    out.write(sect)
                    out.write("]\n")
                    label = False
                out.write(opt)
                out.write(vi)
                newval = self.unconvert(sect, opt)
                out.write(newval.replace("\n", "\n\t"))
                out.write('\n')
                written.append((sect, opt))

    def load_defaults(self, defaults):
        '''Load default values (stored in Options.py).'''
        for section, opts in defaults.items():
            for opt in opts:
                # If first item of the tuple is a sub-class of Option, then
                # instantiate that (with the rest as args).  Otherwise,
                # assume standard Options class.
                klass = Option
                args = opt
                try:
                    if issubclass(opt[0], Option):
                        klass = opt[0]
                        args = opt[1:]
                except TypeError: # opt[0] not a class
                    pass

                o = klass(*args)
                self._options[section, o.name] = o

    def set_restore_point(self):
        '''Remember what the option values are right now, to
        be able to go back to them, via revert_to_restore_point().

        Any existing restore point is wiped.  Restore points do
        not persist over sessions.
        '''
        self.restore_point = {}
        for key, opt_obj in self._options.iteritems():
            self.restore_point[key] = opt_obj.get()

    def revert_to_restore_point(self):
        '''Restore option values to their values when set_restore_point()
        was last called.

        If set_restore_point() has not been called, then this has no
        effect.  If new options have been added since set_restore_point,
        their values are not effected.
        '''
        for key, value in self.restore_point.iteritems():
            self._options[key].set(value)

    def merge_files(self, file_list):
        for f in file_list:
            self.merge_file(f)

    def convert_and_set(self, section, option, value):
        value = self.convert(section, option, value)
        self.set(section, option, value)

    def merge_file(self, filename):
        import ConfigParser
        c = ConfigParser.ConfigParser()
        c.read(filename)
        for sect in c.sections():
            for opt in c.options(sect):
                value = c.get(sect, opt)
                section = sect
                option = opt
                if not self._options.has_key((section, option)):
                    if option.startswith('x-'):
                        # try setting option without the x- prefix
                        option = option[2:]
                        if self._options.has_key((section, option)):
                            self.convert_and_set(section, option, value)
                        # not an error if an X- option is missing
                    else:
                        option = 'x-' + option
                        # going the other way, if the option has been
                        # deprecated, set its x-prefixed version and
                        # emit a warning
                        if self._options.has_key((section, option)):
                            self.convert_and_set(section, option, value)
                            self._report_deprecated_error(section, opt)
                        else:
                            print >> sys.stderr, (
                                "warning: Invalid option %s in"
                                " section %s in file %s" %
                                (opt, sect, filename))
                else:
                    self.convert_and_set(section, option, value)

    # not strictly necessary, but convenient shortcuts to self._options
    def display_name(self, sect, opt):
        '''A name for the option suitable for display to a user.'''
        return self._options[sect, opt.lower()].display_name()
    def default(self, sect, opt):
        '''The default value for the option.'''
        return self._options[sect, opt.lower()].default()
    def doc(self, sect, opt):
        '''Documentation for the option.'''
        return self._options[sect, opt.lower()].doc()
    def valid_input(self, sect, opt):
        '''Valid values for the option.'''
        return self._options[sect, opt.lower()].valid_input()
    def no_restore(self, sect, opt):
        '''Do not restore this option when restoring to defaults.'''
        return self._options[sect, opt.lower()].no_restore()
    def is_valid(self, sect, opt, value):
        '''Check if this is a valid value for this option.'''
        return self._options[sect, opt.lower()].is_valid(value)
    def multiple_values_allowed(self, sect, opt):
        '''Multiple values are allowed for this option.'''
        return self._options[sect, opt.lower()].multiple_values_allowed()

    def is_boolean(self, sect, opt):
        '''The option is a boolean value. (Support for Python 2.2).'''
        return self._options[sect, opt.lower()].is_boolean()

    def convert(self, sect, opt, value):
        '''Convert value from a string to the appropriate type.'''
        return self._options[sect, opt.lower()].convert(value)

    def unconvert(self, sect, opt):
        '''Convert value from the appropriate type to a string.'''
        return self._options[sect, opt.lower()].unconvert()

    def get_option(self, sect, opt):
        '''Get an option.'''
        if self.conversion_table.has_key((sect, opt)):
            sect, opt = self.conversion_table[sect, opt]
        return self._options[sect, opt.lower()]

    def get(self, sect, opt):
        '''Get an option value.'''
        if self.conversion_table.has_key((sect, opt.lower())):
            sect, opt = self.conversion_table[sect, opt.lower()]
        return self.get_option(sect, opt.lower()).get()

    def __getitem__(self, key):
        return self.get(key[0], key[1])

    def set(self, sect, opt, val=None):
        '''Set an option.'''
        if self.conversion_table.has_key((sect, opt.lower())):
            sect, opt = self.conversion_table[sect, opt.lower()]
            
        # Annoyingly, we have a special case.  The notate_to and
        # notate_subject allowed values have to be set to the same
        # values as the header_x_ options, but this can't be done
        # (AFAIK) dynmaically. If this isn't the case, then if the
        # header_x_string values are changed, the notate_ options don't
        # work.  Outlook Express users like both of these options...so
        # we fix it here. See also sf #944109.
        # This code was originally in Options.py, after loading in the
        # options.  But that doesn't work, because if we are setting
        # both in a config file, we need it done immediately.
        # We now need the hack here, *and* in UserInterface.py
        # For the moment, this will do.  Use a real mail client, for
        # goodness sake!
        if sect == "Headers" and opt in ("notate_to", "notate_subject"):
            self._options[sect, opt.lower()].set(val)
            return
        if self.is_valid(sect, opt, val):
            self._options[sect, opt.lower()].set(val)
        else:
            print >> sys.stderr, ("Attempted to set [%s] %s with "
                                  "invalid value %s (%s)" %
                                  (sect, opt.lower(), val, type(val)))

    def set_from_cmdline(self, arg, stream=None):
        """Set option from colon-separated sect:opt:val string.

        If optional stream arg is not None, error messages will be displayed
        on stream, otherwise KeyErrors will be propagated up the call chain.
        """
        sect, opt, val = arg.split(':', 2)
        opt = opt.lower()
        try:
            val = self.convert(sect, opt, val)
        except (KeyError, TypeError), msg:
            if stream is not None:
                self._report_option_error(sect, opt, val, stream, msg)
            else:
                raise
        else:
            self.set(sect, opt, val)

    def _report_deprecated_error(self, sect, opt):
        print >> sys.stderr, (
            "Warning: option %s in section %s is deprecated" %
            (opt, sect))

    def _report_option_error(self, sect, opt, val, stream, msg):
        if sect in self.sections():
            vopts = self.options(True)
            vopts = [v.split(']', 1)[1] for v in vopts
                       if v.startswith('[%s]'%sect)]
            if opt not in vopts:
                print >> stream, "Invalid option:", opt
                print >> stream, "Valid options for", sect, "are:"
                vopts = ', '.join(vopts)
                vopts = wrap(vopts)
                for line in vopts:
                    print >> stream, '  ', line
            else:
                print >> stream, "Invalid value:", msg
        else:
            print >> stream, "Invalid section:", sect
            print >> stream, "Valid sections are:"
            vsects = ', '.join(self.sections())
            vsects = wrap(vsects)
            for line in vsects:
                print >> stream, '  ', line

    def __setitem__(self, key, value):
        self.set(key[0], key[1], value)

    def sections(self):
        '''Return an alphabetical list of all the sections.'''
        all = []
        for sect, opt in self._options.keys():
            if sect not in all:
                all.append(sect)
        all.sort()
        return all

    def options_in_section(self, section):
        '''Return an alphabetical list of all the options in this section.'''
        all = []
        for sect, opt in self._options.keys():
            if sect == section:
                all.append(opt)
        all.sort()
        return all

    def options(self, prepend_section_name=False):
        '''Return an alphabetical list of all the options, optionally
        prefixed with [section_name]'''
        all = []
        for sect, opt in self._options.keys():
            if prepend_section_name:
                all.append('[' + sect + ']' + opt)
            else:
                all.append(opt)
        all.sort()
        return all

    def display(self, add_comments=False):
        '''Display options in a config file form.'''
        output = StringIO.StringIO()
        keys = self._options.keys()
        keys.sort()
        currentSection = None
        for sect, opt in keys:
            if sect != currentSection:
                if currentSection is not None:
                    output.write('\n')
                output.write('[')
                output.write(sect)
                output.write("]\n")
                currentSection = sect
            if add_comments:
                doc = self._options[sect, opt].doc()
                if not doc:
                    doc = "No information available, sorry."
                doc = re.sub(r"\s+", " ", doc)
                output.write("\n# %s\n" % ("\n# ".join(wrap(doc)),))
            self._options[sect, opt].write_config(output)
        return output.getvalue()

    def _display_nice(self, section, option, formatter):
        '''Display a nice output of the options'''
        # Given that the Options class is no longer as nice looking
        # as it once was, this returns all the information, i.e.
        # the doc, default values, and so on
        output = StringIO.StringIO()

        # when section and option are both specified, this
        # is nothing more than a call to as_nice_string
        if section is not None and option is not None:
            opt = self._options[section, option.lower()]
            output.write(getattr(opt, formatter)(section))
            return output.getvalue()

        all = self._options.keys()
        all.sort()
        for sect, opt in all:
            if section is not None and sect != section:
                continue
            opt = self._options[sect, opt.lower()]
            output.write(getattr(opt, formatter)(sect))
        return output.getvalue()

    def display_full(self, section=None, option=None):
        '''Display options including all information.'''
        return self._display_nice(section, option, 'as_nice_string')
        
    def output_for_docs(self, section=None, option=None):
        '''Return output suitable for inserting into documentation for
        the available options.'''
        return self._display_nice(section, option, 'as_documentation_string')

# These are handy references to commonly used regex/tuples defining
# permitted values. Although the majority of options use one of these,
# you may use any regex or tuple you wish.
HEADER_NAME = r"[\w\.\-\*]+"
HEADER_VALUE = r".+"
INTEGER = r"[\d]+"              # actually, a *positive* integer
REAL = r"[\d]+[\.]?[\d]*"       # likewise, a *positive* real
BOOLEAN = (False, True)
SERVER = r"([\w\.\-]+(:[\d]+)?)"  # in the form server:port
PORT = r"[\d]+"
EMAIL_ADDRESS = r"[\w\-\.]+@[\w\-\.]+"
PATH = r"[\w \$\.\-~:\\/\*\@\=]+"
VARIABLE_PATH = PATH + r"%"
FILE = r"[\S]+"
FILE_WITH_PATH = PATH
IP_LIST = r"\*|localhost|((\*|[01]?\d\d?|2[0-4]\d|25[0-5])\.(\*|[01]?\d" \
          r"\d?|2[0-4]\d|25[0-5])\.(\*|[01]?\d\d?|2[0-4]\d|25[0-5])\.(\*" \
          r"|[01]?\d\d?|2[0-4]\d|25[0-5]),?)+"
# IMAP seems to allow any character at all in a folder name,
# but we want to use the comma as a delimiter for lists, so
# we don't allow this.  If anyone has folders with commas in the
# names, please let us know and we'll figure out something else.
# ImapUI.py prints out a warning if this is the case.
IMAP_FOLDER = r"[^,]+"

# IMAP's astring should also be valid in the form:
#   "{" number "}" CRLF *CHAR8
#   where number represents the number of CHAR8 octets
# but this is too complex for us at the moment.
IMAP_ASTRING = []
for _i in xrange(1, 128):
    if chr(_i) not in ['"', '\\', '\n', '\r']:
        IMAP_ASTRING.append(chr(_i))
del _i
IMAP_ASTRING = r"\"?[" + re.escape(''.join(IMAP_ASTRING)) + r"]+\"?"

# Similarly, each option must specify whether it should be reset to
# this value on a "reset to defaults" command.  Most should, but with some
# like a server name that defaults to "", this would be pointless.
# Again, for ease of reading, we define these here:
RESTORE = True
DO_NOT_RESTORE = False

OCRAD_CHARSET = r"ascii|iso-8859-9|iso-8859-15"
