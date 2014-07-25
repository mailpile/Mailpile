import gettext
from gettext import translation, gettext, NullTranslations
from jinja2 import Environment, BaseLoader, TemplateNotFound


ACTIVE_TRANSLATION = None


def gettext(string):
    if not ACTIVE_TRANSLATION:
        return string
    return ACTIVE_TRANSLATION.gettext(string).decode('utf-8')


def ngettext(string1, string2, n):
    if not ACTIVE_TRANSLATION:
        return string1 if (n == 1) else string2
    return ACTIVE_TRANSLATION.ngettext(string1, string2, n).decode('utf-8')


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
    global ACTIVE_TRANSLATION

    trans = None
    if language:
        try:
            trans = translation("mailpile", config.getLocaleDirectory(),
                                [language], codeset="utf-8")
        except IOError:
            if session:
                session.ui.warning(('Failed to load language %s'
                                    ) % language)
    if not trans:
        trans = translation("mailpile", config.getLocaleDirectory(),
                            codeset='utf-8', fallback=True)

        if session and isinstance(trans, NullTranslations):
            session.ui.warning('Failed to configure i18n. '
                               'Using fallback.')

    if trans:
        ACTIVE_TRANSLATION = trans
        trans.set_output_charset("utf-8")

        if hasattr(config, 'jinja_env'):
            config.jinja_env.install_gettext_translations(trans,
                                                          newstyle=True)

        if session and language:
            session.ui.debug(gettext('Loaded language %s') % language)

    return trans
