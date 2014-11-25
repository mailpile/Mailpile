from mailpile.i18n import gettext as _
from mailpile.i18n import ngettext as _n
from mailpile.i18n import ACTIVE_TRANSLATION, RECENTLY_TRANSLATED
from mailpile.commands import Command


class I18NRecent(Command):
    """Show recently translated string in context"""
    ORDER = ('', 0)
    SYNOPSIS = (None, 'i18n/recent', 'i18n/recent', '')
    HTTP_CALLABLE = ('GET', )
    HTTP_QUERY_VARS = {}

    class CommandResult(Command.CommandResult):
        def as_text(self):
            if self.result:
                return '\n'.join(["%s: %s" % (key, value) for key, value in self.result.iteritems()])
            else:
                return _("Nothing recently translated")

    def command(self):
        return dict(map(lambda x: (x, _(x)), RECENTLY_TRANSLATED))

