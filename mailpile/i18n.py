import gettext
import os
import threading
from gettext import translation, gettext, NullTranslations
from jinja2 import Environment, BaseLoader, TemplateNotFound


ACTIVE_TRANSLATION = None

RECENTLY_TRANSLATED_LOCK = threading.Lock()
RECENTLY_TRANSLATED = []

FORMAT_CHECKED = {}


# This little doodad will on-the-fly check whether our translators
# messed up our format strings in various ways, and suppress the
# translation if it is obviously broken.
def _fmt_safe(translation, original):
    global FORMAT_CHECKED
    if translation in FORMAT_CHECKED:
        return FORMAT_CHECKED[translation]
    if '%' in original:
        try:
            assert(len([c for c in translation if c == '%'])
                   == len([c for c in original if c == '%']))
            bogon = translation % 1
            FORMAT_CHECKED[translation] = translation
        except TypeError:
            # This just means we gave the wrong argument or the wrong
            # number of arguments - so the format string itself is OK.
            FORMAT_CHECKED[translation] = translation
        except:
            FORMAT_CHECKED[translation] = original
    else:
        FORMAT_CHECKED[translation] = translation
    return FORMAT_CHECKED[translation]


def gettext(string):
    with RECENTLY_TRANSLATED_LOCK:
        global RECENTLY_TRANSLATED
        RECENTLY_TRANSLATED = [t for t in RECENTLY_TRANSLATED[-100:]
                               if t != string] + [string]
    if not ACTIVE_TRANSLATION:
        return string

    # FIXME: What if our input is utf-8?  Does gettext want us to
    #        encode it first, or send the UTF-8 string?  Since we are
    #        not encoding it, the decode below may fail. :(
    translation = ACTIVE_TRANSLATION.gettext(string)
    try:
        translation = translation.decode('utf-8')
    except UnicodeEncodeError:
        pass

    return _fmt_safe(translation, string)


def ngettext(string1, string2, n):
    with RECENTLY_TRANSLATED_LOCK:
        global RECENTLY_TRANSLATED
        RECENTLY_TRANSLATED = [t for t in RECENTLY_TRANSLATED[-100:]
                               if t not in (string1, string2)
                               ] + [string1, string2]

    default = string1 if (n == 1) else string2
    if not ACTIVE_TRANSLATION:
        return default

    # FIXME: What if our input is utf-8?  Does gettext want us to
    #        encode it first, or send the UTF-8 string?  Since we are
    #        not encoding it, the decode below may fail. :(
    translation = ACTIVE_TRANSLATION.ngettext(string1, string2, n)
    try:
        translation = translation.decode('utf-8')
    except UnicodeEncodeError:
        pass

    return _fmt_safe(translation, default)


class i18n_disabler:
    def __init__(self):
        self.stack = []

    def __enter__(self):
        global ACTIVE_TRANSLATION
        self.stack.append(ACTIVE_TRANSLATION)
        ACTIVE_TRANSLATION = None

    def __exit__(self, *args, **kwargs):
        global ACTIVE_TRANSLATION
        ACTIVE_TRANSLATION = self.stack.pop(-1)


i18n_disabled = i18n_disabler()


def ActivateTranslation(session, config, language):
    global ACTIVE_TRANSLATION, RECENTLY_TRANSLATED

    trans = None
    if language:
        try:
            trans = translation("mailpile", config.getLocaleDirectory(),
                                [language], codeset="utf-8")
        except IOError:
            if session and language[:2] != 'en':
                session.ui.debug('Failed to load language %s' % language)

    if not trans:
        trans = translation("mailpile", config.getLocaleDirectory(),
                            codeset='utf-8', fallback=True)

        if (session and language[:2] != 'en'
                and isinstance(trans, NullTranslations)):
            session.ui.debug('Failed to configure i18n. '
                             'Using fallback.')

    if trans:
        with RECENTLY_TRANSLATED_LOCK:
            RECENTLY_TRANSLATED = []
        ACTIVE_TRANSLATION = trans
        trans.set_output_charset("utf-8")

        if hasattr(config, 'jinja_env'):
            config.jinja_env.install_gettext_translations(trans,
                                                          newstyle=True)

        if session and language and not isinstance(trans, NullTranslations):
            session.ui.debug(gettext('Loaded language %s') % language)

    return trans


def ListTranslations(config):
    locales = config.getLocaleDirectory()
    languages = {}
    for lang in os.listdir(locales):
        try:
            with open(os.path.join(locales, lang,
                                   'LC_MESSAGES', 'mailpile.po')) as fd:
                for line in fd.read(8192).splitlines():
                    if line[1:].startswith('Language-Team: '):
                        languages[lang] = ' '.join([word for word in
                                                    line[1:-2].split()[1:-1]]
                                                   ).replace('LANGUAGE', lang)
        except (IOError, OSError):
            pass
    return languages
