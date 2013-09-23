import mailpile.plugins
from mailpile.commands import Command

from mailpile.plugins.tags import Tag, Filter
from mailpile.plugins.contacts import *


##[ Search terms ]############################################################

def search(config, term, hits):
    group = config.vcards.get(term.split(':', 1)[1])
    rt, emails = [], []
    if group and group.kind == 'group':
        for email, attrs in group.get('EMAIL', []):
            group = config.vcards.get(email.lower(), None)
            if group:
                emails.extend([e[0].lower() for e in group.get('EMAIL', [])])
            else:
                emails.append(email.lower())
    fromto = term.startswith('group:') and 'from' or 'to'
    for email in set(emails):
        rt.extend(hits('%s:%s' % (email, fromto)))
    return rt

mailpile.plugins.register_search_term('group', search)
mailpile.plugins.register_search_term('togroup', search)


##[ Commands ]################################################################

def GroupVCard(parent):
    """A factory for generating group commands"""

    class GroupVCardCommand(parent):
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
            return (Tag(session, arg=['add', handle]).run() and
                    Filter(session, arg=['add', 'group:%s' % handle,
                                         '+%s' % handle, vcard.fn]).run())

        def _add_from_messages(self):
            raise ValueError('Invalid group ids: %s' % self.args)

        def _pre_delete_vcard(self, vcard):
            session, handle = self.session, vcard.nickname
            return (Filter(session, arg=['delete',
                                         'group:%s' % handle]).run() and
                    Tag(session, arg=['delete', handle]).run())

    return GroupVCardCommand


class Group(GroupVCard(VCard)):
    """View groups"""
    TEMPLATE_IDS = ['group']
    HTTP_CALLABLE = ('GET', )


class AddGroup(GroupVCard(AddVCard)):
    """Add groups"""
    KIND = 'group'
    ORDER = ('Tagging', 3)
    TEMPLATE_IDS = ['group/add']
    HTTP_CALLABLE = ('POST', )


class SetGroup(GroupVCard(SetVCard)):
    """Add groups"""
    TEMPLATE_IDS = ['group/set']
    HTTP_CALLABLE = ('UPDATE', )


class RemoveGroup(GroupVCard(RemoveVCard)):
    """Add groups"""
    TEMPLATE_IDS = ['group/remove']
    HTTP_CALLABLE = ('POST', )


class ListGroups(GroupVCard(ListVCards)):
    """Find groups"""
    TEMPLATE_IDS = ['group/list']
    HTTP_CALLABLE = ('GET', )


mailpile.plugins.register_command('G:',     'group=',        Group)
mailpile.plugins.register_command('_gradd', 'group/add=',    AddGroup)
mailpile.plugins.register_command('_grset', 'group/set=',    SetGroup)
mailpile.plugins.register_command('_grdel', 'group/remove=', RemoveGroup)
mailpile.plugins.register_command('_grlst', 'group/list=',   ListGroups)
