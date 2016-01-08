import re
import time

from mailpile.i18n import gettext as _
from mailpile.i18n import ngettext as _n
from mailpile.commands import Command
from mailpile.mailutils import Email
from mailpile.util import truthy

# FIXME: Perhaps this plugin should be named ESQL and implement an SQL
#        syntax for extracting data from e-mails...
#
#  SELECT from,to,body=Regards\,(.*) FROM search=to:bre
#


class dataDigCommand(Command):
    """Extract tables of structured data from e-mail content"""
    ORDER = ('', 0)
    SYNOPSIS = (None, 'datadig', 'datadig', '<terms ...> -- <messages ...>')
    HTTP_CALLABLE = ('GET', )
    HTTP_QUERY_VARS = {
        'track-id': 'tracking ID for event log',
        'timeout': 'runtime in seconds',
        'header': 'include header',
        'no-mid': 'omit metadata-ID column',
        'term': 'extraction term',
        'mid': 'metadata-ID'
    }

    class CommandResult(Command.CommandResult):
        def as_text(self):
            if self.result:
                return '\n'.join(['\t'.join([unicode(cell) for cell in row])
                                  for row in self.result])
            else:
                return _("Nothing Happened")

    def _filter(self, idx, e, celldata, filters):
        if not isinstance(celldata, (list, tuple)):
            celldata = [celldata]
        for fltr in filters:
            # FIXME!
            celldata = celldata
        return celldata

    def _cell(self, idx, e, cellspec):
        filters = cellspec.split('||')
        cspec, lcspec = filters[0], filters[0].lower()
        lcspec = lcspec.split(':', 1)[0].split('=', 1)[-1]

        if lcspec == 'sender':
            return self._filter(idx, e, e.get_msg_info(field=idx.MSG_FROM),
                                filters)

        if lcspec == 'subject':
            return self._filter(idx, e, e.get_msg_info(field=idx.MSG_SUBJECT),
                                filters)

        if lcspec in ('from', 'to', 'cc', 'bcc', 'date'):
            return self._filter(idx, e, e.get_msg()[lcspec], filters)

        if lcspec in ('text', ):
            rxp = cspec.split(':', 1)[1]
            if lcspec == 'text':
                body = e.get_editing_strings()['body']
                mobj = re.search(rxp, body)
            if mobj:
                return self._filter(idx, e, list(mobj.groups()), filters)

        return ['']

    def command(self):
        session, config, idx = self.session, self.session.config, self._idx()

        # Command-line arguments...
        msgs = list(self.args)
        timeout = -1
        tracking_id = None
        with_header = False
        without_mid = False
        columns = []
        while msgs and msgs[0].lower() != '--':
            arg = msgs.pop(0)
            if arg.startswith('--timeout='):
                timeout = float(arg[10:])
            elif arg.startswith('--header'):
                with_header = True
            elif arg.startswith('--no-mid'):
                without_mid = True
            else:
                columns.append(arg)
        if msgs and msgs[0].lower() == '--':
            msgs.pop(0)

        # Form arguments...
        timeout = float(self.data.get('timeout', [timeout])[0])
        with_header |= truthy(self.data.get('header', [''])[0])
        without_mid |= truthy(self.data.get('no-mid', [''])[0])
        tracking_id = self.data.get('track-id', [tracking_id])[0]
        columns.extend(self.data.get('term', []))
        msgs.extend(['=%s' % mid.replace('=', '')
                     for mid in self.data.get('mid', [])])

        # Add a header to the CSV if requested
        if with_header:
            results = [[col.split('||')[0].split(':', 1)[0].split('=', 1)[0]
                        for col in columns]]
            if not without_mid:
                results[0] = ['MID'] + results[0]
        else:
            results = []

        deadline = (time.time() + timeout) if (timeout > 0) else None
        msg_idxs = self._choose_messages(msgs)
        progress = []
        for msg_idx in msg_idxs:
            e = Email(idx, msg_idx)
            if self.event and tracking_id:
                progress.append(msg_idx)
                self.event.private_data = {"progress": len(progress),
                                           "track-id": tracking_id,
                                           "total": len(msg_idxs),
                                           "reading": e.msg_mid()}
                self.event.message = _('Digging into =%s') % e.msg_mid()
                self._update_event_state(self.event.RUNNING, log=True)
            else:
                session.ui.mark(_('Digging into =%s') % e.msg_mid())
            row = [] if without_mid else ['%s' % e.msg_mid()]
            for cellspec in columns:
                row.extend(self._cell(idx, e, cellspec))
            results.append(row)
            if deadline and deadline < time.time():
                break

        return self._success(_('Found %d rows in %d messages'
                               ) % (len(results), len(msg_idxs)), results)

