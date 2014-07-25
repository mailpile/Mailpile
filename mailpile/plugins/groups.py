from mailpile.commands import Command
from mailpile.i18n import gettext as _
from mailpile.i18n import ngettext as _n
from mailpile.plugins import PluginManager
from mailpile.plugins.tags import AddTag, DeleteTag, Filter
from mailpile.plugins.contacts import *


_plugins = PluginManager(builtin=__file__)


##[ Search terms ]############################################################

def search(config, idx, term, hits):
    group = config._vcards.get(term.split(':', 1)[1])
    rt, emails = [], []
    if group and group.kind == 'group':
        for email, attrs in group.get('EMAIL', []):
            group = config._vcards.get(email.lower(), None)
            if group:
                emails.extend([e[0].lower() for e in group.get('EMAIL', [])])
            else:
                emails.append(email.lower())
    fromto = term.startswith('group:') and 'from' or 'to'
    for email in set(emails):
        rt.extend(hits('%s:%s' % (email, fromto)))
    return rt

_plugins.register_search_term('group', search)
_plugins.register_search_term('togroup', search)


##[ Commands ]################################################################

def GroupVCard(parent):
    """A factory for generating group commands"""

    class GroupVCardCommand(parent):
        SYNOPSIS = tuple([(t and t.replace('vcard', 'group') or t)
                          for t in parent.SYNOPSIS])
        KIND = 'group'
        ORDER = ('Tagging', 4)

        def _valid_vcard_handle(self, vc_handle):
            # If there is already a tag by this name, complain.
            return (vc_handle and
                   ('-' != vc_handle[0]) and
                   ('@' not in vc_handle) and
                   (not self.session.config.get_tag_id(vc_handle)))

        def _prepare_new_vcard(self, vcard):
            session, handle = self.session, vcard.nickname
            return (AddTag(session, arg=[handle]).run() and
                    Filter(session, arg=['add', 'group:%s' % handle,
                                         '+%s' % handle, vcard.fn]).run())

        def _add_from_messages(self):
            raise ValueError('Invalid group ids: %s' % self.args)

        def _pre_delete_vcard(self, vcard):
            session, handle = self.session, vcard.nickname
            return (Filter(session, arg=['delete',
                                         'group:%s' % handle]).run() and
                    DeleteTag(session, arg=[handle]).run())

    return GroupVCardCommand


class Group(GroupVCard(VCard)):
    """View groups"""


class AddGroup(GroupVCard(AddVCard)):
    """Add groups"""


class GroupAddLines(GroupVCard(VCardAddLines)):
    """Add lines to a group VCard"""


class RemoveGroup(GroupVCard(RemoveVCard)):
    """Remove groups"""


class ListGroups(GroupVCard(ListVCards)):
    """Find groups"""


_plugins.register_commands(Group, AddGroup, GroupAddLines,
                           RemoveGroup, ListGroups)
