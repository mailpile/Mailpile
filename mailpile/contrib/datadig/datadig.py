import re

from mailpile.i18n import gettext as _
from mailpile.i18n import ngettext as _n
from mailpile.commands import Command
from mailpile.mailutils import Email

# FIXME: Perhaps this plugin should be named ESQL and implement an SQL
#        syntax for extracting data from e-mails...
#
#  SELECT from,to,body=Regards\,(.*) FROM search=to:bre
#


class dataDigCommand(Command):
    """Extract tables of structured data from e-mail content"""
    ORDER = ('', 0)
    SYNOPSIS = (None, 'datadig', 'datadig', '<things ...> -- <messages ...>')
    HTTP_CALLABLE = ('GET', )
    HTTP_QUERY_VARS = {}

    class CommandResult(Command.CommandResult):
        def as_text(self):
            if self.result:
                return '\n'.join(['\t'.join([unicode(cell) for cell in row])
                                  for row in self.result])
            else:
                return _("Nothing Happened")

    def _filter(self, idx, e, thing, filters):
        if not isinstance(thing, (list, tuple)):
            thing = [thing]
        for fltr in filters:
            thing = thing
        return thing

    def _thing(self, idx, e, thing):
        filters = thing.split('|')
        thing, lthing = filters[0], filters[0].lower()
        if lthing == 'from':
            return self._filter(idx, e, e.get_msg_info(field=idx.MSG_FROM),
                                filters)
        if lthing == 'subject':
            return self._filter(idx, e, e.get_msg_info(field=idx.MSG_SUBJECT),
                                filters)
        if lthing in ('to', 'cc', 'bcc', 'list', 'received'):
            return self._filter(idx, e, e.get_msg()[lthing], filters)
        if lthing.startswith('text:'):
            rxp = re.compile(thing[5:])
            body = e.get_editing_strings()['body']
            mobj = re.search(rxp, body)
            if mobj:
                return self._filter(idx, e, list(mobj.groups()), filters)
        return []

    def command(self):
        session, config, idx = self.session, self.session.config, self._idx()
        args = list(self.args)

        things = []
        while args and args[0].lower() != '--':
            things.append(args.pop(0))
        if args and args[0].lower() == '--':
            args.pop(0)
        msg_idxs = self._choose_messages(args)

        results = []
        for msg_idx in msg_idxs:
            e = Email(idx, msg_idx)
            session.ui.mark(_('Digging into =%s') % e.msg_mid())
            row = ['=%s' % e.msg_mid()]
            for thing in things:
                row.extend(self._thing(idx, e, thing))
            results.append(row)

        return self._success(_('Found %d rows in %d messages'
                               ) % (len(results), len(msg_idxs)), results)

