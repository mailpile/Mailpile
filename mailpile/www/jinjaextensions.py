import copy
import datetime
import hashlib
import random
import re
import urllib
import json
import shlex
import time
from jinja2 import nodes, UndefinedError, Markup
from jinja2.ext import Extension
from jinja2.utils import contextfunction, import_string, escape

#from markdown import markdown

from mailpile.commands import Action
from mailpile.defaults import APPVER
from mailpile.i18n import gettext as _
from mailpile.i18n import ngettext as _n
from mailpile.util import *
from mailpile.ui import HttpUserInteraction
from mailpile.urlmap import UrlMap
from mailpile.plugins import PluginManager
from mailpile.vcard import AddressInfo


VERSION_IDENTIFIER = None

# This looks for a .git folder and uses the current state to augment
# our version... cachebusting during development.
dirname, tail = os.path.split(__file__)
while dirname and tail and os.path.exists(dirname):
    fetch_head = os.path.join(dirname, '.git', 'FETCH_HEAD')
    if os.path.exists(fetch_head):
        try:
            md5 = md5_hex(open(fetch_head, 'r').read())
            VERSION_IDENTIFIER = '%s-%s' % (APPVER, md5[:8])
            break
        except (OSError, IOError):
            break
    dirname, tail = os.path.split(dirname)


class MailpileCommand(Extension):
    """Run Mailpile Commands, """
    tags = set(['mpcmd'])

    def __init__(self, environment):
        Extension.__init__(self, environment)
        e = self.env = environment
        s = self
        e.globals['mailpile'] = s._command
        e.globals['mailpile_render'] = s._command_render
        e.globals['U'] = s._url_path_fix
        e.globals['make_rid'] = randomish_uid
        e.globals['is_dev_version'] = s._is_dev_version
        e.globals['version_identifier'] = s._version_identifier
        e.filters['random'] = s._random
        e.globals['random'] = s._random
        e.filters['truthy'] = s._truthy
        e.globals['truthy'] = s._truthy
        e.filters['with_context'] = s._with_context
        e.globals['with_context'] = s._with_context
        e.filters['url_path_fix'] = s._url_path_fix
        e.globals['use_data_view'] = s._use_data_view
        e.globals['regex_replace'] = s._regex_replace
        e.filters['regex_replace'] = s._regex_replace
        e.globals['friendly_bytes'] = s._friendly_bytes
        e.filters['friendly_bytes'] = s._friendly_bytes
        e.globals['friendly_number'] = s._friendly_number
        e.filters['friendly_number'] = s._friendly_number
        e.globals['show_avatar'] = s._show_avatar
        e.filters['show_avatar'] = s._show_avatar
        e.globals['navigation_on'] = s._navigation_on
        e.filters['navigation_on'] = s._navigation_on
        e.globals['has_label_tags'] = s._has_label_tags
        e.filters['has_label_tags'] = s._has_label_tags
        e.globals['show_message_signature'] = s._show_message_signature
        e.filters['show_message_signature'] = s._show_message_signature
        e.globals['show_message_encryption'] = s._show_message_encryption
        e.filters['show_message_encryption'] = s._show_message_encryption
        e.globals['show_text_part_signature'] = s._show_text_part_signature
        e.filters['show_text_part_signature'] = s._show_text_part_signature
        e.globals['show_text_part_encryption'] = s._show_text_part_encryption
        e.filters['show_text_part_encryption'] = s._show_text_part_encryption
        e.globals['show_crypto_policy'] = s._show_crypto_policy
        e.filters['show_crypto_policy'] = s._show_crypto_policy
        e.globals['contact_url'] = s._contact_url
        e.filters['contact_url'] = s._contact_url
        e.globals['contact_name'] = s._contact_name
        e.filters['contact_name'] = s._contact_name
        e.globals['thread_upside_down'] = s._thread_upside_down
        e.filters['thread_upside_down'] = s._thread_upside_down
        e.globals['fix_urls'] = s._fix_urls
        e.filters['fix_urls'] = s._fix_urls

        # See utils.py for these functions:
        e.globals['elapsed_datetime'] = elapsed_datetime
        e.filters['elapsed_datetime'] = elapsed_datetime
        e.globals['friendly_datetime'] = friendly_datetime
        e.filters['friendly_datetime'] = friendly_datetime
        e.globals['friendly_time'] = friendly_time
        e.filters['friendly_time'] = friendly_time

        # These are helpers for injecting plugin elements
        e.globals['get_ui_elements'] = s._get_ui_elements
        e.globals['ui_elements_setup'] = s._ui_elements_setup
        e.globals['add_state_query_string'] = s._add_state_query_string
        e.filters['add_state_query_string'] = s._add_state_query_string

        # This is a worse versin of urlencode, but without it we require
        # Jinja 2.7, which isn't apt-get installable.
        e.globals['urlencode'] = s._urlencode
        e.filters['urlencode'] = s._urlencode
        # Same thing for selectattr
        e.globals['selectattr'] = s._selectattr
        e.filters['selectattr'] = s._selectattr

        # Make a function-version of the safe command
        e.globals['safe'] = s._safe
        e.filters['json'] = s._json
        e.filters['escapejs'] = s._escapejs

        # Strip trailing blank lines from email
        e.globals['nice_text'] = s._nice_text
        e.filters['nice_text'] = s._nice_text

        # Transforms \n into HTML <br />
        e.globals['to_br'] = s._to_br
        e.filters['to_br'] = s._to_br

        # Strip Re: Fwd: from subject lines
        e.globals['nice_subject'] = s._nice_subject
        e.filters['nice_subject'] = s._nice_subject
        # And [list] headings as well
        e.globals['bare_subject'] = s._bare_subject
        e.filters['bare_subject'] = s._bare_subject

        # Make unruly names a lil bit nicer
        e.globals['nice_name'] = s._nice_name
        e.filters['nice_name'] = s._nice_name

        # Makes a UI usable classification of attachment from mimetype
        e.globals['attachment_type'] = s._attachment_type
        e.filters['attachment_type'] = s._attachment_type

        # Loads theme settings JSON manifest
        e.globals['theme_settings'] = s._theme_settings
        e.filters['theme_settings'] = s._theme_settings

        # Separates Fingerprint in 4 char groups
        e.globals['nice_fingerprint'] = s._nice_fingerprint
        e.filters['nice_fingerprint'] = s._nice_fingerprint

        # Converts Filter +/- tags into arrays
        e.globals['make_filter_groups'] = s._make_filter_groups
        e.filters['make_filter_groups'] = s._make_filter_groups

        # Make Nice Summary of Recipients
        e.globals['recipient_summary'] = s._recipient_summary
        e.filters['recipient_summary'] = s._recipient_summary

        # Nagifications
        e.globals['show_nagification'] = s._show_nagification
        e.filters['show_nagification'] = s._show_nagification

    def _debug(self, msg):
        if 'jinja' in self.env.session.config.sys.debug:
            sys.stderr.write('jinja: ')
            sys.stderr.write(msg)
            sys.stderr.write('\n')
            sys.stderr.flush()

    def _command(self, command, *args, **kwargs):
        rv = Action(self.env.session, command, args, data=kwargs).as_dict()
        self._debug('mailpile(%s, %s, %s) -> %s'
                    % (command, args, kwargs, rv))
        return rv

    def _command_render(self, how, command, *args, **kwargs):
        self._debug('mailpile_render(%s, %s, ...)' % (how, command))
        old_ui, config = self.env.session.ui, self.env.session.config
        try:
            ui = self.env.session.ui = HttpUserInteraction(None, config,
                                                           log_parent=old_ui,
                                                           log_prefix='jinja/')
            ui.html_variables = copy.deepcopy(old_ui.html_variables)
            ui.render_mode = how
            ui.display_result(Action(self.env.session, command, args,
                                     data=kwargs))
            rv = ui.render_response(config)
            return (rv[0], rv[1].strip())
        finally:
            self.env.session.ui = old_ui

    def _use_data_view(self, view_name, result):
        self._debug('use_data_view(%s, ...)' % (view_name))
        dv = UrlMap(self.env.session).map(None, 'GET', view_name, {}, {})[-1]
        return dv.view(result)

    def _get_ui_elements(self, ui_type, state, context=None):
        self._debug('get_ui_element(%s, %s, ...)' % (ui_type, state))
        ctx = context or state.get('context_url', '')
        return copy.deepcopy(PluginManager().get_ui_elements(ui_type, ctx))

    @classmethod
    def _add_state_query_string(cls, url, state, elem=None):
        if not url:
            url = state.get('command_url', '')
        if '#' in url:
            url, frag = url.split('#', 1)
            frag = '#' + frag
        else:
            frag = ''
        if url:
            args = []
            query_args = state.get('query_args', {})
            for key in sorted(query_args.keys()):
                if key.startswith('_'):
                    continue
                values = query_args[key]
                if elem:
                    for rk, rv in elem.get('url_args_remove', []):
                        if rk == key:
                            values = [v for v in values if rv and (v != rv)]
                if elem:
                    for ak, av in elem.get('url_args_add', []):
                        if ak == key and av not in values:
                            values.append(av)
                args.extend([(key, unicode(v).encode("utf-8")) for v in values])
            return url + '?' + urllib.urlencode(args) + frag
        else:
            return url + frag

    def _ui_elements_setup(self, classfmt, elements):
        self._debug('ui_elements_setup(%s, %s)' % (classfmt, elements))
        setups = []
        for elem in elements:
            if elem.get('javascript_setup'):
                setups.append('$("%s").each(function(){%s(this);});'
                              % (classfmt % elem, elem['javascript_setup']))
            if elem.get('javascript_events'):
                for event, call in elem.get('javascript_events').iteritems():
                    setups.append('$("%s").bind("%s", %s);' %
                        (classfmt % elem, event, call))
        return Markup("function(){%s}" % ''.join(setups))

    def _regex_replace(self, s, find, replace):
        """A non-optimal implementation of a regex filter"""
        return re.sub(find, replace, s)

    def _friendly_number(self, number, decimals=0):
        # See mailpile/util.py:friendly_number if this needs fixing
        return friendly_number(number, decimals=decimals, base=1000)

    def _friendly_bytes(self, number, decimals=0):
        # See mailpile/util.py:friendly_number if this needs fixing
        return friendly_number(number,
                               decimals=decimals, base=1024, suffix='B')

    def _show_avatar(self, contact):
        if "photo" in contact:
            photo = contact['photo']
        else:
            photo = ('%s/static/img/avatar-default.png'
                     % self.env.session.config.sys.http_path)
        return photo

    def _navigation_on(self, search_tag_ids, on_tid):
        if search_tag_ids:
            for tid in search_tag_ids:
                if tid == on_tid:
                    return "navigation-on"
                else:
                    return ""

    def _has_label_tags(self, tags, tag_tids):
        self._debug('has_label_tags(..., %s, ...)' % (tag_tids,))
        count = 0
        for tid in tag_tids:
            if tags[tid]["label"] and not tags[tid]["searched"]:
                count += 1
        return count

    _DEFAULT_SIGNATURE = [
            "crypto-color-gray",
            "icon-signature-none",
            _("Unknown"),
            _("There is something unknown or wrong with this signature")]
    _STATUS_SIGNATURE = {
        "none": [
            "crypto-color-gray",
            "icon-signature-none",
            _("Not Signed"),
            _("This data has no digital signature, which means it could "
              "have come from anyone, not necessarily the real sender")],
        "error": [
            "crypto-color-red",
            "icon-signature-error",
            _("Error"),
            _("There was a weird error with this digital signature")],
        "mixed-error": [
            "crypto-color-red",
            "icon-signature-error",
            _("Mixed Error"),
            _("Parts of this message have a signature with a weird error")],
        "invalid": [
            "crypto-color-red",
            "icon-signature-invalid",
            _("Invalid"),
            _("The digital signature was invalid or bad")],
        "mixed-invalid": [
            "crypto-color-red",
            "icon-signature-invalid",
            _("Mixed Invalid"),
            _("Parts of this message have a digital signature that is invalid"
              " or bad")],
        "revoked": [
            "crypto-color-red",
            "icon-signature-revoked",
            _("Revoked"),
            _("Watch out, the digital signature was made with a key that has been "
              "revoked - this is not a good thing")],
        "mixed-revoked": [
            "crypto-color-red",
            "icon-signature-revoked",
            _("Mixed Revoked"),
            _("Watch out, parts of this message were digitally signed with a key "
              "that has been revoked")],
        "expired": [
            "crypto-color-orange",
            "icon-signature-expired",
            _("Expired"),
            _("The digital signature was made with an expired key")],
        "mixed-expired": [
            "crypto-color-orange",
            "icon-signature-expired",
            _("Mixed Expired"),
            _("Parts of this message have a digital signature made with an "
              "expired key")],
        "unknown": [
            "crypto-color-gray",
            "icon-signature-unknown",
            _("Unknown"),
            _("The digital signature was made with an unknown key, so we can not "
              "verify it")],
        "mixed-unknown": [
            "crypto-color-gray",
            "icon-signature-unknown",
            _("Mixed Unknown"),
            _("Parts of this message have a signature made with an unknown "
              "key which we can not verify")],
        "unverified": [
            "crypto-color-blue",
            "icon-signature-unverified",
            _("Unverified"),
            _("The signature was good but it came from a key that is not "
              "verified yet")],
        "mixed-unverified": [
            "crypto-color-blue",
            "icon-signature-unverified",
            _("Mixed Unverified"),
            _("Parts of this message have an unverified signature")],
        "verified": [
            "crypto-color-green",
            "icon-signature-verified",
            _("Verified"),
            _("The signature was good and came from a verified key, w00t!")],
        "mixed-verified": [
            "crypto-color-blue",
            "icon-signature-verified",
            _("Mixed Verified"),
            _("Parts of the message have a verified signature, but other "
              "parts do not")]
    }

    @classmethod
    def _show_text_part_signature(self, status):
        # Within a text part, mixed state is equivalent to no encryption, and
        # no signature - the signed/encrypted parts are explictly marked.
        try:
            if status and status.startswith('mixed-'):
                status = 'none'
        except UndefinedError:
            status = 'none'
        return self._show_message_signature(status)

    @classmethod
    def _show_message_signature(self, status):
        # This avoids crashes when attributes are missing.
        try:
            if status.startswith('hack the planet'):
                pass
        except UndefinedError:
            status = ''

        color, icon, text, message = self._STATUS_SIGNATURE.get(status, self._DEFAULT_SIGNATURE)

        return {
            'color': color,
            'icon': icon,
            'text': text,
            'message': message
        }

    _DEFAULT_ENCRYPTION = [
        "crypto-color-gray",
        "icon-lock-open",
        _("Unknown"),
        _("There is some unknown thing wrong with this encryption")]
    _STATUS_ENCRYPTION = {
        "none": [
            "crypto-color-gray",
            "icon-lock-open",
            _("Not Encrypted"),
            _("This content was not encrypted. It could have been intercepted "
              "and read by an unauthorized party")],
        "decrypted": [
            "crypto-color-green",
            "icon-lock-closed",
            _("Encrypted"),
            _("This content was encrypted, great job being secure")],
        "mixed-decrypted": [
            "crypto-color-blue",
            "icon-lock-closed",
            _("Mixed Encrypted"),
            _("Part of this message were encrypted, but other parts were not "
              "encrypted")],
        "lockedkey": [
            "crypto-color-green",
            "icon-lock-closed",
            _("Locked Key"),
            _("You have the encryption key to decrypt this, "
              "but the key itself is locked.")],
        "mixed-lockedkey": [
            "crypto-color-green",
            "icon-lock-closed",
            _("Mixed Locked Key"),
            _("Parts of the message could not be decrypted because your "
              "encryption key is locked.")],
        "missingkey": [
            "crypto-color-red",
            "icon-lock-closed",
            _("Missing Key"),
            _("You don't have the encryption key to decrypt this, "
              "perhaps it was encrypted to an old key you don't have anymore?")],
        "mixed-missingkey": [
            "crypto-color-red",
            "icon-lock-closed",
            _("Mixed Missing Key"),
            _("Parts of the message could not be decrypted because you "
              "are missing the private key. Perhaps it was encrypted to an "
              "old key you don't have anymore?")],
        "error": [
            "crypto-color-red",
            "icon-lock-error",
            _("Error"),
            _("We failed to decrypt and are unsure why.")],
        "mixed-error": [
            "crypto-color-red",
            "icon-lock-error",
            _("Mixed Error"),
            _("We failed to decrypt parts of this message and are unsure why")]
    }

    @classmethod
    def _show_text_part_encryption(self, status):
        # Within a text part, mixed state is equivalent to no encryption, and
        # no signature - the signed/encrypted parts are explictly marked.
        try:
            if status and status.startswith('mixed-'):
                status = 'none'
        except UndefinedError:
            status = 'none'
        return self._show_message_encryption(status)

    @classmethod
    def _show_message_encryption(self, status):
        # This avoids crashes when attributes are missing.
        try:
            if status.startswith('hack the planet'):
                pass
        except UndefinedError:
            status = ''

        color, icon, text, message = self._STATUS_ENCRYPTION.get(status, self._DEFAULT_ENCRYPTION)

        return {
            'color': color,
            'icon': icon,
            'text': text,
            'message': message
        }

    _DEFAULT_CRYPTO_POLICY = [
        _("Automatic"),
        _("Mailpile will intelligently try to guess and suggest the best "
          "security with this given contact")]
    _CRYPTO_POLICY = {
        "default": [
            _("Automatic"),
            _("Mailpile will intelligently try to guess and suggest the best "
              "security with this given contact")],
        "none": [
            _("Don't Sign or Encrypt"),
            _("Messages will not be encrypted nor signed by your encryption key")],
        "sign": [
            _("Only Sign"),
            _("Messages will only be signed by your encryption key")],
        "encrypt": [
            _("Only Encrypt"),
            _("Messages will only be encrypted but not signed by your encryption key")],
        "sign-encrypt": [
            _("Always Encrypt & Sign"),
            _("Messages will be both encrypted and signed by your encryption key")]
    }

    @classmethod
    def _show_crypto_policy(self, policy):
        # This avoids crashes when attributes are missing.
        try:
            if policy.startswith('hack the planet'):
                pass
        except UndefinedError:
            policy = ''

        text, message = self._CRYPTO_POLICY.get(policy, self._DEFAULT_CRYPTO_POLICY)

        return {
            'text': text,
            'message': message
        }

    def _contact_url(self, person):
        if not self._is_dev_version():
            return ('%s/search/?q=email:%s'
                    ) % (self.env.session.config.sys.http_path,
                         person['address'])

        if 'contact' in person['flags']:
            url = ("%s/contacts/view/%s/"
                   % (self.env.session.config.sys.http_path,
                      person['address']))
        else:
            url = "%s/#add-contact" % self.env.session.config.sys.http_path
        return url

    def _contact_name(self, person):
        self._debug('contact_name(%s)' % (person,))
        name = person['fn']
        if (not name or '@' in name) and person.get('email'):
            vcard = self.env.session.config.vcards.get_vcard(person['email'])
            if vcard:
                return vcard.fn
        return name

    @classmethod
    def _thread_upside_down(self, thread):
        return [(i, flip_unicode_boxes(a), c) for i, a, c in reversed(thread)]

    URL_RE_HTTP = re.compile('(<a [^>]*?)'            # 1: <a
                             '(href=["\'])'           # 2:    href="
                             '(https?:[^>]+)'         # 3:  URL!
                             '(["\'][^>]*>)'          # 4:          ">
                             '(.*?)'                  # 5:  Description!
                             '(</a>)')                # 6: </a>

    # We deliberately leave the https:// prefix on, because it is both
    # rare and worth drawing attention to.
    URL_RE_HTTP_PROTO = re.compile('(?i)^https?://((w+\d*|[a-z]+\d+)\.)?')

    URL_RE_MAILTO = re.compile('(<a [^>]*?)'          # 1: <a
                               '(href=["\']mailto:)'  # 2:    href="mailto:
                               '([^"]+)'              # 3:  Email address!
                               '(["\'][^>]*>)'        # 4:          ">
                               '(.*?)'                # 5:  Description!
                               '(</a>)')              # 6: </a>

    URL_DANGER_ALERT = ('onclick=\'return confirm("' +
                        _("Mailpile security tip: \\n\\n"
                          "  Uh oh! This web site may be dangerous!\\n"
                          "  Are you sure you want to continue?\\n") +
                        '");\'')

    def _fix_urls(self, text, truncate=45, danger=False):
        def http_fixer(m):
            url = m.group(3)
            odesc = desc = m.group(5)
            url_danger = danger

            if len(desc) > truncate:
                desc = desc[:truncate-3] + '...'
                noproto = re.sub(self.URL_RE_HTTP_PROTO, '', desc)
                if ('/' not in noproto) and ('?' not in noproto):
                    # Phishers sometimes create subdomains that look like
                    # something legit: yourbank.evil.com.
                    # So, if the domain was getting truncated reveal the TLD
                    # even if that means overflowing our truncation request.
                    noproto = re.sub(self.URL_RE_HTTP_PROTO, '', odesc)
                    if '/' in noproto:
                        desc = '.'.join(noproto.split('/')[0]
                                        .rsplit('.', 3)[-2:]) + '/...'
                    else:
                        desc = '.'.join(noproto.split('?')[0]
                                        .rsplit('.', 3)[-2:]) + '/...'
                    url_danger = True

            return ''.join([m.group(1),
                            url_danger and self.URL_DANGER_ALERT or '',
                            ' target=_blank ',
                            m.group(2), url, m.group(4), desc, m.group(6)])

        def mailto_fixer(m):
            return ''.join([m.group(1), 'href="mailto:', m.group(3),
                            '" class="compose-to-email">',
                            m.group(5), m.group(6)])

        return Markup(re.sub(self.URL_RE_HTTP, http_fixer,
                             re.sub(self.URL_RE_MAILTO, mailto_fixer,
                                    text)))

    def _random(self, sequence):
        return sequence[random.randint(0, len(sequence)-1)]

    @classmethod
    def _truthy(cls, txt, default=False):
        return truthy(txt, default=default)

    @classmethod
    def _is_dev_version(cls):
        return ('dev' in APPVER or 'github' in APPVER or 'test' in APPVER)

    @classmethod
    def _version_identifier(cls):
        return VERSION_IDENTIFIER or APPVER

    def _with_context(self, sequence, context=1):
        return [[(sequence[j] if (0 <= j < len(sequence)) else None)
                 for j in range(i - context, i + context + 1)]
                for i in range(0, len(sequence))]

    def _url_path_fix(self, *urlparts):
        url = ''.join([unicode(p) for p in urlparts])
        if url[:1] in ('/', ):
            http_path = self.env.session.config.sys.http_path or ''
            if not url.startswith(http_path):
                url = http_path + url
        return self._safe(url)

    def _urlencode(self, s):
        if type(s) == 'Markup':
            s = s.unescape()
        return Markup(urllib.quote_plus(s.encode('utf-8')))

    def _selectattr(self, seq, attr, value=None):
        if value is None:
            return [s for s in seq if s.get(attr)]
        else:
            return [s for s in seq if s.get(attr) == value]

    def _safe(self, s):
        if type(s) == 'Markup':
            return s.unescape()
        else:
            return Markup(s).unescape()

    def _json(self, d):
        json = self.env.session.ui.render_json(d)
        # These are necessary so the browser doesn't get confused by things
        # when JSON is included directly into the HTML as a <script>.
        json = json.replace('<', '\\x3c')
        json = json.replace('&', '\\x26')
        return json

    _JS_ESCAPES = (
            ('\\', '\\x5c'),
            ('\'', '\\x27'),
            ('"', '\\x22'),
            ('>', '\\x3e'),
            ('<', '\\x3c'),
            ('&', '\\x26'),
            ('=', '\\x3d'),
            ('-', '\\x2d'),
            (';', '\\x3b'),
    )

    def _escapejs(self, value):
        """ Hex encodes some characters for use in JavaScript strings.

        Lightly inspired from https://github.com/django/django/blame/ebc773ada3e4f40cf5084268387b873d7fe22e8b/django/utils/html.py#L63
        """
        for bad, good in self._JS_ESCAPES:
            value = value.replace(bad, good)
        return self._safe(value)

    @classmethod
    def _nice_text(self, text):
        trimmed = ''
        previous = 'not'
        for line in text.splitlines():
            if line or previous == 'not':
                trimmed += line + '\n'
                if line:
                    previous = 'not'
                else:
                    previous = 'blank'
        return trimmed.strip()

    _TEXT_LINEBREAK_RE = re.compile(r'(?:\r\n|\r|\n)')

    @classmethod
    def _to_br(self, text):
        """ Replaces \n by <br />

        Inspired from http://jinja.pocoo.org/docs/dev/api/#custom-filters
        """
        result = '<br />'.join(p for p in self._TEXT_LINEBREAK_RE.split(escape(text)))
        return Markup(result)

    @classmethod
    def _nice_subject(self, metadata):
        if metadata['subject']:
            output = re.sub('(?i)^((re|fw|fwd|aw|wg):\s+)+', '', metadata['subject'])
        else:
            output = '(' + _("No Subject") + ')'
        return output

    @classmethod
    def _bare_subject(self, metadata):
        if metadata['subject']:
            output = re.sub('(?i)^((re|fw|fwd|aw|wg):\s+|\[\S+\]\s+)+', '', metadata['subject'])
        else:
            output = '(' + _("No Subject") + ')'
        return output

    @classmethod
    def _nice_name(self, name, truncate=100):
        if len(name) > truncate:
            name = name[:truncate-3] + '...'
        return name

    @classmethod
    def _recipient_summary(self, editing_strings, addresses, truncate):
        summary_list = []
        recipients = (editing_strings['to_aids'] +
                      editing_strings['cc_aids'] +
                      editing_strings['bcc_aids'])
        for aid in recipients:
            summary_list.append(addresses[aid].fn)
        summary = ', '.join(summary_list)
        if len(summary) > truncate:
            others = ''
            if len(recipients) > 1:
                others = _("and %d others") % (len(recipients) - 1)
            summary = summary[:truncate] + '... ' + others
        return summary

    @classmethod
    def _attachment_type(self, mime):
        if mime in [
            "application/octet-stream",
            "application/mac-binhex40",
            "application/x-shockwave-flash",
            "application/x-director",
            "application/x-x509-ca-cert",
            "application/x-director",
            "application/x-msdownload",
            "application/x-director"
            ]:
            attachment = "application"
        elif mime in [
            "application/x-compress",
            "application/x-compressed",
            "application/x-tar",
            "application/zip",
            "application/x-stuffit",
            "application/x-gzip",
            "application/x-gzip-compressed",
            "application/x-tar",
            "application/x-winzip",
            "application/x-zip",
            "application/x-zip-compressed"
            ]:
            attachment = "archive"
        elif mime in [
            "audio/midi",
            "audio/mid",
            "audio/mpeg",
            "audio/basic",
            "audio/x-aiff",
            "audio/x-pn-realaudio",
            "audio/x-pn-realaudio",
            "audio/mid",
            "audio/basic",
            "audio/x-wav",
            "audio/x-mpegurl",
            "audio/wave",
            "audio/wav"
            ]:
            attachment = "audio"
        elif mime in [
            "text/x-vcard"
            ]:
            attachment = "contact"
        elif mime in [
            "image/bmp",
            "image/gif",
            "image/jpeg",
            "image/pjpeg",
            "image/svg+xml",
            "image/x-png",
            "image/png"
            ]:
            attachment = "image-visible"
        elif mime in [
            "image/cis-cod",
            "image/ief",
            "image/pipeg",
            "image/tiff",
            "image/x-cmx",
            "image/x-cmu-raster",
            "image/x-rgb",
            "image/x-icon",
            "image/x-xbitmap",
            "image/x-xpixmap",
            "image/x-xwindowdump",
            "image/x-portable-anymap",
            "image/x-portable-graymap",
            "image/x-portable-pixmap",
            "image/x-portable-bitmap",
            "application/x-photoshop",
            "application/postscript"
            ]:
            attachment = "image"
        elif mime in [
            "application/pgp-signature"
            ]:
            attachment = "signature"
        elif mime in [
            "application/pgp-keys"
            ]:
            attachment = "keys"
        elif mime in [
            "application/rtf",
            "application/vnd.ms-works",
            "application/msword",
            "application/pdf",
            "application/x-download",
            "message/rfc822",
            "text/scriptlet",
            "text/plain",
            "text/iuls",
            "text/plain",
            "text/richtext",
            "text/x-setext",
            "text/x-component",
            "text/webviewhtml",
            "text/h323"
            ]:
            attachment = "document"
        elif mime in [
            "application/x-javascript",
            "text/html",
            "text/css",
            "text/xml",
            "text/json"
            ]:
            attachment = "code"
        elif mime in [
            "application/excel",
            "application/msexcel",
            "application/vnd.ms-excel",
            "application/vnd.msexcel",
            "application/csv",
            "application/x-csv",
            "text/tab-separated-values",
            "text/x-comma-separated-values",
            "text/comma-separated-values",
            "text/csv",
            "text/x-csv"
            ]:
            attachment = "spreadsheet"
        elif mime in [
            "application/powerpoint",
            "application/vnd.ms-powerpoint"
            ]:
            attachment = "slideshow"
        elif mime in [
            "video/quicktime",
            "video/x-sgi-movie",
            "video/mpeg",
            "video/x-la-asf",
            "video/x-ms-asf",
            "video/x-msvideo"
            ]:
            attachment = "video"
        else:
            attachment = "unknown"
        return attachment

    def _theme_settings(self):
        self._debug('theme_settings()')
        path, handle, mime = self.env.session.config.open_file('html_theme', 'theme.json')
        return json.load(handle)

    def _nice_fingerprint(self, fingerprint):
        if fingerprint:
            slices = [fingerprint[i:i + 4] for i in range(0, len(fingerprint), 4)]
            output = ""
            for group in slices:
                output += group + " "
            return output
        else:
            return _("No Fingerprint")

    def _make_filter_groups(self, tags):
        split = shlex.split(tags)
        output = dict();
        add = []
        remove = []
        for item in split:
            out = item.strip('+-')
            if item[0] == "+":
                add.append(out)
            elif item[0] == "-":
                remove.append(out)
        output['add'] = add
        output['remove'] = remove
        return output

    def _show_nagification(self, nag):
        now = long((time.time() + 0.5) * 1000)
        if now > nag and nag != -1:
            return True
        return False
