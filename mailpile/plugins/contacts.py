import os
import random
import time
from email import encoders

import mailpile.config.defaults
import mailpile.security as security
from mailpile.crypto.gpgi import GnuPG
from mailpile.crypto.gpgi import GnuPGBaseKeyGenerator, GnuPGKeyGenerator
from mailpile.crypto.autocrypt_utils import generate_autocrypt_setup_code
from mailpile.plugins import EmailTransform, PluginManager
from mailpile.commands import Command, Action
from mailpile.eventlog import Event
from mailpile.i18n import gettext as _
from mailpile.i18n import ngettext as _n
from mailpile.mailutils.addresses import AddressHeaderParser
from mailpile.mailutils.emails import Email, ExtractEmails, ExtractEmailAndName
from mailpile.security import SecurePassphraseStorage
from mailpile.vcard import VCardLine, VCardStore, MailpileVCard, AddressInfo
from mailpile.util import *


_plugins = PluginManager(builtin=__file__)

GLOBAL_VCARD_LOCK = VCardRLock()


##[ VCards ]########################################

class VCardCommand(Command):
    VCARD = "vcard"
    IS_USER_ACTIVITY = True
    WITH_CONTEXT = (GLOBAL_VCARD_LOCK,)

    class CommandResult(Command.CommandResult):
        IGNORE = ('line_id', 'pid', 'x-rank')

        def as_text(self):
            try:
                return self._as_text()
            except (KeyError, ValueError, IndexError, TypeError):
                return ''

        def _as_text(self):
            if isinstance(self.result, dict):
                co = self.command_obj
                if co.VCARD in self.result:
                    return self._vcards_as_text([self.result[co.VCARD]])
                if co.VCARD + 's' in self.result:
                    return self._vcards_as_text(self.result[co.VCARD + 's'])
            return Command.CommandResult.as_text(self)

        def _vcards_as_text(self, result):
            lines = []
            b64re = re.compile('base64,.*$')
            for card in result:
                if isinstance(card, list):
                    for line in card:
                        key = line.name
                        data = re.sub(b64re, _('(BASE64 ENCODED DATA)'),
                                      unicode(line[key]))
                        attrs = ', '.join([('%s=%s' % (k, v))
                                           for k, v in line.attrs
                                           if k not in ('pid',)])
                        if attrs:
                            attrs = ' (%s)' % attrs
                        lines.append('%3.3s %-5.5s %s: %s%s'
                                     % (line.line_id,
                                        line.get('pid', ''),
                                        key, data, attrs))
                    lines.append('')
                else:
                    emails = [k['email'] for k in card['email']]
                    photos = [k['photo'] for k in card.get('photo', [])]
                    lines.append('%s %-32.32s %s'
                                 % (photos and ':)' or '  ',
                                    card['fn'] + (' (%s)' % card['note']
                                                  if card.get('note') else ''),
                                    ', '.join(emails)))
                    for key in [k['key'].split(',')[-1]
                                for k in card.get('key', [])]:
                        lines.append('   %-32.32s key:%s' % ('', key))
            return '\n'.join(lines)

    def _form_defaults(self):
        return {'form': self.HTTP_POST_VARS}

    def _make_new_vcard(self, handle, name, note, kind):
        l = [VCardLine(name='fn', value=name),
             VCardLine(name='kind', value=kind)]
        if note:
            l.append(VCardLine(name='note', value=note))
        if kind in VCardStore.KINDS_PEOPLE:
            return MailpileVCard(VCardLine(name='email',
                                           value=handle, type='pref'), *l,
                                 config=self.session.config)
        else:
            return MailpileVCard(VCardLine(name='nickname', value=handle), *l,
                                 config=self.session.config)

    def _valid_vcard_handle(self, vc_handle):
        return (vc_handle and '@' in vc_handle[1:])

    def _pre_delete_vcard(self, vcard):
        pass

    def _vcard_list(self, vcards, mode='mpCard', info=None, simplify=False):
        info = info or {}
        if mode == 'lines':
            data = [x.as_lines() for x in vcards if x]
        else:
            data = [x.as_mpCard() for x in vcards if x]

        # Generate some helpful indexes for finding stuff
        by_email = {}
        by_rid = {}
        for count, vc in enumerate(vcards):
            by_rid[vc.random_uid] = count
            by_email[vc.email] = count
        for count, vc in enumerate(vcards):
            for vcl in vc.get_all('EMAIL'):
                if vcl.value not in by_email:
                    by_email[vcl.value] = count

        # Simplify lists when there is only one element?
        if simplify and len(data) == 1:
            data = data[0]
            whatsit = self.VCARD
        else:
            whatsit = self.VCARD + 's'

        info.update({
            whatsit: data,
            "emails": by_email,
            "rids": by_rid,
            "count": len(vcards)
        })
        return info


class VCard(VCardCommand):
    """Display a single vcard"""
    SYNOPSIS = (None, 'vcards/view', None, '<nickname>')
    ORDER = ('Internals', 6)
    KIND = ''

    def command(self, save=True):
        self._idx()  # Make sure VCards are all loaded
        session, config = self.session, self.session.config
        vcards = []
        for email in self.args:
            vcard = config.vcards.get_vcard(email)
            if vcard:
                vcards.append(vcard)
            else:
                session.ui.warning('No such %s: %s' % (self.VCARD, email))
        return self._success(_('Found %d results') % len(vcards),
                             result=self._vcard_list(vcards, simplify=True))


class AddVCard(VCardCommand):
    """Add one or more vcards"""
    SYNOPSIS = (None, 'vcards/add', None, '[all] <msgs> OR <email> = <name>')
    ORDER = ('Internals', 6)
    KIND = ''
    HTTP_CALLABLE = ('POST', 'PUT', 'GET')
    HTTP_POST_VARS = {
        'email': 'E-mail address',
        'name': 'Contact name',
        'note': 'Note about contact',
        'mid': 'Message ID'
    }
    COMMAND_SECURITY = security.CC_CHANGE_CONTACTS

    IGNORED_EMAILS_AND_DOMAINS = (
        'reply.airbnb.com',
        'notifications@github.com'
    )

    def _add_from_messages(self, args, add_recipients):
        pairs, idx = [], self._idx()
        for email in [Email(idx, i) for i in self._choose_messages(args)]:
            msg_info = email.get_msg_info()
            pairs.append(ExtractEmailAndName(msg_info[idx.MSG_FROM]))
            if add_recipients:
                people = (idx.expand_to_list(msg_info) +
                          idx.expand_to_list(msg_info, field=idx.MSG_CC))
                for e in people:
                    pair = ExtractEmailAndName(e)
                    domain = pair[0].split('@')[-1]
                    if (pair[0] not in self.IGNORED_EMAILS_AND_DOMAINS and
                            domain not in self.IGNORED_EMAILS_AND_DOMAINS and
                            'noreply' not in pair[0]):
                        pairs.append(pair)
        return [(p1, p2, '') for p1, p2 in pairs]

    def _sanity_check(self, kind, vcard):
        pass

    def _before_vcard_create(self, kind, triplets):
        return {}

    def _after_vcard_create(self, kind, vcard, state):
        pass

    def command(self, recipients=False, quietly=False, internal=False):
        idx = self._idx()  # Make sure VCards are all loaded
        session, config = self.session, self.session.config
        args = list(self.args)

        if self.data.get('_method', 'not-http').upper() == 'GET':
            return self._success(_('Add contacts here!'),
                                 self._form_defaults())

        if (len(args) > 2
                and args[1] == '='
                and self._valid_vcard_handle(args[0])):
            handle = args[0]
            name = []
            note = []
            inname = True
            for v in args[2:]:
                if v.startswith('('):
                    inname = False
                    v = v[1:]
                if v.endswith(')'):
                    v = v[:-1]
                if inname:
                    name.append(v)
                else:
                    note.append(v)

            triplets = [(args[0], ' '.join(name), ' '.join(note))]

        elif self.data:
            if self.data.get('email'):
                emails = self.data["email"]
                names = self.data["name"][:]
                names.extend(['' for i in range(len(names), len(emails))])
                notes = self.data.get("note", [])[:]
                notes.extend(['' for i in range(len(notes), len(emails))])
                triplets = zip(emails, names, notes)
            elif self.data.get('mid'):
                mids = self.data.get('mid')
                triplets = self._add_from_messages(
                    ['=%s' % mid.replace('=', '') for mid in mids])
        else:
            if args and args[0] == 'all':
                recipients = args.pop(0) and True
            triplets = self._add_from_messages(args, recipients)

        if triplets:
            vcards = []
            kind = self.KIND if not internal else 'internal'

            self._sanity_check(kind, triplets)
            state = self._before_vcard_create(kind, triplets)

            for handle, name, note in triplets:
                vcard = config.vcards.get(handle.lower())
                if vcard:
                    if not quietly:
                        session.ui.warning('Already exists: %s' % handle)
                    if kind != 'profile' and vcard.kind != 'internal':
                        continue

                if vcard and vcard.kind == 'internal':
                    config.vcards.deindex_vcard(vcard)
                    vcard.email = handle.lower()
                    vcard.name = name
                    vcard.note = note
                    vcard.kind = kind
                else:
                    vcard = self._make_new_vcard(handle.lower(), name, note,
                                                 kind)
                self._after_vcard_create(kind, vcard, state)
                config.vcards.add_vcards(vcard)
                vcards.append(vcard)
            if state.get('save_config', False):
                self._background_save(config=True)
        else:
            return self._error('Nothing to do!')
        return self._success(_('Added %d contacts') % len(vcards),
            result=self._vcard_list(vcards, simplify=True))


class RemoveVCard(VCardCommand):
    """Delete vcards"""
    SYNOPSIS = (None, 'vcards/remove', None, '<email|x-mailpile-rid>')
    ORDER = ('Internals', 6)
    KIND = ''
    HTTP_CALLABLE = ('POST', 'DELETE')
    HTTP_POST_VARS = {
        'email': 'delete by e-mail',
        'rid': 'delete by x-mailpile-rid'
    }
    COMMAND_SECURITY = security.CC_CHANGE_CONTACTS

    def command(self):
        idx = self._idx()  # Make sure VCards are all loaded
        session, config = self.session, self.session.config
        removed = []
        for handle in (list(self.args) +
                       self.data.get('email', []) +
                       self.data.get('rid', [])):
            vcard = config.vcards.get_vcard(handle)
            if vcard:
                self._pre_delete_vcard(vcard)
                config.vcards.del_vcards(vcard)
                removed.append(handle)
            else:
                session.ui.error(_('No such contact: %s') % handle)
        if removed:
            return self._success(_('Removed contacts: %s')
                                 % ', '.join(removed))
        else:
            return self._error(_('No contacts found'))


class VCardAddLines(VCardCommand):
    """Add a lines to a VCard"""
    SYNOPSIS = (None,
                'vcards/addlines', 'vcards/addlines',
                '<email> <[[<NR>]=]line> ...')
    ORDER = ('Internals', 6)
    KIND = ''
    HTTP_CALLABLE = ('POST', 'UPDATE')
    HTTP_POST_VARS = {
        'email': 'update by e-mail',
        'rid': 'update by x-mailpile-rid',
        'name': 'Line name',
        'value': 'Line value',
        'replace': 'int=replace line by number',
        'replace_all': 'Boolean: replace all lines, or not',
        'client': 'Source of this change'
    }
    COMMAND_SECURITY = security.CC_CHANGE_CONTACTS
    DEFAULT_REPLACE_ALL = False

    def _get_vcard(self, handle):
        return self.session.config.vcards.get_vcard(handle)

    def command(self):
        idx = self._idx()  # Make sure VCards are all loaded
        session, config = self.session, self.session.config

        if self.args:
            handle, lines = self.args[0], self.args[1:]
        else:
            handle = self.data.get('rid', self.data.get('email', [None]))[0]
            if not handle:
                raise ValueError('Must set rid or email to choose VCard')
            name, value, replace, replace_all = (self.data.get(n, [None])[0]
                for n in ('name', 'value', 'replace', 'replace_all'))
            if not name or not value or ':' in name or '=' in name:
                raise ValueError('Must send a line name and line data')
            value = '%s:%s' % (name, value)
            if replace:
                value = '%d=%s' % (replace, value)
            elif truthy(replace_all, default=self.DEFAULT_REPLACE_ALL):
                value = '=' + value
            lines = [value]

        vcard = self._get_vcard(handle)
        if not vcard:
            return self._error('%s not found: %s' % (self.VCARD, handle))
        config.vcards.deindex_vcard(vcard)
        client = self.data.get('client', [vcard.USER_CLIENT])[0]
        try:
            for l in lines:
                lname = l.split(':', 1)[0].lower()
                if lname[0] == '=':
                    l = l[1:].strip()
                    lname = lname[1:]
                    removing = [ex._line_id for ex in vcard.get_all(lname)]
                elif lname in MailpileVCard.MPCARD_SINGLETONS:
                    removing = [ex._line_id for ex in vcard.get_all(lname)]
                else:
                    removing = []

                if '=' in l[:5]:
                    ln, l = l.split('=', 1)
                    vcard.set_line(int(ln.strip()), VCardLine(l.strip()),
                                   client=client)

                else:
                    if removing:
                        vcard.remove(*removing)
                    vcard.add(VCardLine(l), client=client)

            vcard.save()
            return self._success(_("Added %d lines") % len(lines),
                result=self._vcard_list([vcard], simplify=True, info={
                    'updated': handle,
                    'added': len(lines)
                }))
        except KeyboardInterrupt:
            raise
        except:
            config.vcards.index_vcard(vcard)
            self._ignore_exception()
            return self._error(_('Error adding lines to %s') % handle)
        finally:
            config.vcards.index_vcard(vcard)


class VCardSet(VCardAddLines):
    """Add a lines to a VCard, ensuring VCard exists"""
    SYNOPSIS = (None, 'vcards/set', 'vcards/set', '<email> <[[<NR>]=]line> ...')
    HTTP_POST_VARS = dict_merge(VCardAddLines.HTTP_POST_VARS, {
        'fn': 'Name on card'
    })
    DEFAULT_REPLACE_ALL = True

    def _get_vcard(self, handle):
        vcard = self.session.config.vcards.get_vcard(handle)
        if not vcard:
            vcard = self._make_new_vcard(handle,
                                         self.data.get('fn', [handle])[0],
                                         None,
                                         self.KIND or 'individual')
            self.session.config.vcards.add_vcards(vcard)
        return vcard


class VCardRemoveLines(VCardCommand):
    """Remove lines from a VCard"""
    SYNOPSIS = (None, 'vcards/rmlines', None, '<email> <line IDs>')
    ORDER = ('Internals', 6)
    KIND = ''
    HTTP_CALLABLE = ('POST', 'UPDATE')
    COMMAND_SECURITY = security.CC_CHANGE_CONTACTS

    def command(self):
        idx = self._idx()  # Make sure VCards are all loaded
        session, config = self.session, self.session.config

        handle, line_ids = self.args[0], self.args[1:]
        vcard = config.vcards.get_vcard(handle)
        if not vcard:
            return self._error('%s not found: %s' % (self.VCARD, handle))
        config.vcards.deindex_vcard(vcard)
        removed = 0
        try:
            removed = vcard.remove(*[int(li) for li in line_ids])
            vcard.save()
            return self._success(_("Removed %d lines") % removed,
                result=self._vcard_list([vcard], simplify=True, info={
                    'updated': handle,
                    'removed': removed
                }))
        except KeyboardInterrupt:
            raise
        except:
            config.vcards.index_vcard(vcard)
            self._ignore_exception()
            return self._error(_('Error removing lines from %s') % handle)
        finally:
            config.vcards.index_vcard(vcard)


class ListVCards(VCardCommand):
    """Find vcards"""
    SYNOPSIS = (None, 'vcards', None, '[--lines] [<terms>]')
    ORDER = ('Internals', 6)
    KIND = ''
    HTTP_QUERY_VARS = {
        'q': 'search terms',
        'format': 'lines or mpCard (default)',
        'count': 'how many to display (default=40)',
        'offset': 'skip how many in the display (default=0)',
    }
    HTTP_CALLABLE = ('GET')

    def _augment_list_info(self, info):
        return info

    def command(self):
        session, config = self.session, self.session.config
        kinds = self.KIND and [self.KIND] or None
        args = list(self.args)

        if 'format' in self.data:
            fmt = self.data['format'][0]
        elif args and args[0] == '--lines':
            args.pop(0)
            fmt = 'lines'
        else:
            fmt = 'mpCard'

        if 'q' in self.data:
            terms = self.data['q']
        else:
            terms = args

        if 'count' in self.data:
            count = int(self.data['count'][0])
        else:
            count = 120

        if 'offset' in self.data:
            offset = int(self.data['offset'][0])
        else:
            offset = 0

        # If we're loading, stall a bit but then report current state
        loading, loaded = config.vcards.loading, config.vcards.loaded
        if loading:
            time.sleep(2)
            loading, loaded = config.vcards.loading, config.vcards.loaded

        vcards = config.vcards.find_vcards(terms, kinds=kinds)
        total = len(vcards)
        vcards = vcards[offset:offset + count]
        info = self._augment_list_info({
                   'terms': args,
                   'offset': offset,
                   'count': min(count, total),
                   'total': total,
                   'start': offset,
                   'end': offset + min(count, total - offset),
                   'loading': loading,
                   'loaded': loaded})
        return self._success(
            _("Listed %d/%d results") % (min(total, count), total),
            result=self._vcard_list(vcards, mode=fmt, info=info))


def ContactVCard(parent):
    """A factory for generating contact commands"""
    synopsis = [(t and t.replace('vcard', 'contact') or t)
                for t in parent.SYNOPSIS]
    synopsis[2] = synopsis[1]

    class ContactVCardCommand(parent):
        SYNOPSIS = tuple(synopsis)
        KIND = 'individual'
        ORDER = ('Tagging', 3)
        VCARD = "contact"

    return ContactVCardCommand


class Contact(ContactVCard(VCard)):
    """View contacts"""
    SYNOPSIS = (None, 'contacts/view', 'contacts/view', '[<email>]')

    def command(self, save=True):
        contact = VCard.command(self, save)
        # Tee-hee, monkeypatching results.
        contact["sent_messages"] = 0
        contact["received_messages"] = 0
        contact["last_contact_from"] = 10000000000000
        contact["last_contact_to"] = 10000000000000

        for email in contact["contact"]["email"]:
            s = Action(self.session, "search",
                       ["in:Sent", "to:%s" % (email["email"])]).as_dict()
            contact["sent_messages"] += s["result"]["stats"]["total"]
            for mid in s["result"]["thread_ids"]:
                msg = s["result"]["data"]["metadata"][mid]
                if msg["timestamp"] < contact["last_contact_to"]:
                    contact["last_contact_to"] = msg["timestamp"]
                    contact["last_contact_to_msg_url"] = msg["urls"]["thread"]

            s = Action(self.session, "search",
                       ["from:%s" % (email["email"])]).as_dict()
            contact["received_messages"] += s["result"]["stats"]["total"]
            for mid in s["result"]["thread_ids"]:
                msg = s["result"]["data"]["metadata"][mid]
                if msg["timestamp"] < contact["last_contact_from"]:
                    contact["last_contact_from"] = msg["timestamp"]
                    contact["last_contact_from_msg_url"
                            ] = msg["urls"]["thread"]

        if contact["last_contact_to"] == 10000000000000:
            contact["last_contact_to"] = False
            contact["last_contact_to_msg_url"] = ""

        if contact["last_contact_from"] == 10000000000000:
            contact["last_contact_from"] = False
            contact["last_contact_from_msg_url"] = ""

        return contact


class AddContact(ContactVCard(AddVCard)):
    """Add contacts"""


class RemoveContact(ContactVCard(RemoveVCard)):
    """Remove a contact"""


class ListContacts(ContactVCard(ListVCards)):
    SYNOPSIS = (None, 'contacts', 'contacts', '[--lines] [<terms>]')
    """Find contacts"""


class ContactSet(ContactVCard(VCardSet)):
    """Set contact lines, ensuring contact exists"""


class ContactImport(Command):
    """Import contacts"""
    SYNOPSIS = (None, 'contacts/import', 'contacts/import', '[<parameters>]')
    ORDER = ('Internals', 6)
    HTTP_CALLABLE = ('GET', )
    COMMAND_SECURITY = security.CC_CHANGE_CONTACTS

    def command(self, format, terms=None, **kwargs):
        idx = self._idx()  # Make sure VCards are all loaded
        session, config = self.session, self.session.config

        if not format in PluginManager.CONTACT_IMPORTERS.keys():
            session.ui.error("No such import format")
            return False

        importer = PluginManager.CONTACT_IMPORTERS[format]

        if not all([x in kwargs.keys() for x in importer.required_parameters]):
            session.ui.error(
                _("Required parameter missing. Required parameters "
                  "are: %s") % ", ".join(importer.required_parameters))
            return False

        allparams = importer.required_parameters + importer.optional_parameters

        if not all([x in allparams for x in kwargs.keys()]):
            session.ui.error(
                _("Unknown parameter passed to importer. "
                  "Provided %s; but known parameters are: %s"
                  ) % (", ".join(kwargs), ", ".join(allparams)))
            return False

        imp = importer(kwargs)
        if terms:
            contacts = imp.filter_contacts(terms)
        else:
            contacts = imp.get_contacts()

        for importedcontact in contacts:
            # Check if contact exists. If yes, then update. Else create.
            pass


class ContactImporters(Command):
    """Return a list of contact importers"""
    SYNOPSIS = (None, 'contacts/importers', 'contacts/importers', '')
    ORDER = ('Internals', 6)
    HTTP_CALLABLE = ('GET', )

    def command(self):
        res = []
        for iname, importer in CONTACT_IMPORTERS.iteritems():
            r = {}
            r["short_name"] = iname
            r["format_name"] = importer.format_name
            r["format_description"] = importer.format_description
            r["optional_parameters"] = importer.optional_parameters
            r["required_parameters"] = importer.required_parameters
            res.append(r)

        return res


class AddressSearch(VCardCommand):
    """Find addresses (in contacts or mail index)"""
    SYNOPSIS = (None, 'search/address', 'search/address', '[<terms>]')
    ORDER = ('Searching', 6)
    HTTP_QUERY_VARS = {
        'q': 'search terms',
        'count': 'number of results',
        'offset': 'offset results',
        'ms': 'deadline in ms'
    }

    def _boost_rank(self, boost, term, *matches):
        boost = 0.0
        for match in matches:
            match = match.lower()
            if term in match:
                if match.startswith(term):
                    boost += boost * boost * (float(len(term)) / len(match))
                else:
                    boost += boost * (float(len(term)) / len(match))
        return int(boost)

    def _vcard_addresses(self, cfg, terms, ignored_count, deadline):
        addresses = {}
        for vcard in cfg.vcards.find_vcards(terms,
                                            kinds=VCardStore.KINDS_PEOPLE):
            fn = vcard.get('fn')
            for email_vcl in vcard.get_all('email'):
                info = addresses.get(email_vcl.value) or {}
                info.update(AddressInfo(email_vcl.value, fn.value,
                                        vcard=vcard))
                info['rank'] = min(15, info.get('rank', 15))
                addresses[email_vcl.value] = info
                for term in terms:
                    info['rank'] += self._boost_rank(5, term, fn.value,
                                                     email_vcl.value)
            if len(addresses) and time.time() > deadline:
                break

        return addresses.values()

    def _index_addresses(self, cfg, terms, vcard_addresses, count, deadline):
        existing = dict([(k['address'].lower(), k) for k in vcard_addresses])
        index = self._idx()

        # Figure out which tags are invisible so we can skip messages marked
        # with those tags.
        invisible = set([t._key for t in cfg.get_tags(flag_hides=True)])
        matches = {}
        addresses = []

        # 1st, search the social graph for matches, give low priority.
        for frm in index.EMAILS:
            frm_lower = frm.lower()
            match = True
            for term in terms:
                if term not in frm_lower:
                    match = False
                    break
            if match:
                matches[frm] = matches.get(frm, 0) + 3
                if len(matches) > (count * 10):
                    break
            elif len(matches) and time.time() > deadline:
                break

        # 2nd, go through at most the last 5000 messages in the index and
        # search for matching senders or recipients, give medium priority.
        # Note: This is more CPU intensive, so we do this last.
        if len(matches) < (count * 5):
            for msg_idx in xrange(max(0, len(index.INDEX)-5000),
                                  len(index.INDEX)):
                msg_info = index.get_msg_at_idx_pos(msg_idx)
                tags = set(msg_info[index.MSG_TAGS].split(','))
                match = not (tags & invisible)
                if match:
                    frm = msg_info[index.MSG_FROM]
                    search = (frm + ' ' + msg_info[index.MSG_SUBJECT]).lower()
                    for term in terms:
                        if term not in search:
                            match = False
                            break
                    if match:
                        matches[frm] = matches.get(frm, 0) + 1
                        if len(matches) > (count * 5):
                            break
                    if len(matches) and time.time() > deadline:
                        break

        # Assign info & scores!
        for frm in matches:
            email, fn = ExtractEmailAndName(frm)
            boost = min(10, matches[frm])
            for term in terms:
                boost += self._boost_rank(4, term, fn, email)

            if not email or '@' not in email:
                # FIXME: This may not be the right thing for alternate
                #        message transports.
                pass
            elif email.lower() in existing:
                existing[email.lower()]['rank'] += boost
            else:
                info = AddressInfo(email, fn)
                info['rank'] = info.get('rank', 0) + boost
                existing[email.lower()] = info
                addresses.append(info)

        return addresses

    def command(self):
        session, config = self.session, self.session.config

        count = int(self.data.get('count', 10))
        offset = int(self.data.get('offset', 0))
        deadline = time.time() + float(self.data.get('ms', 150)) / 1000.0
        terms = []
        for q in self.data.get('q', []):
            terms.extend(q.lower().split())
        for a in self.args:
            terms.extend(a.lower().split())

        self.session.ui.mark('Searching VCards')
        vcard_addrs = self._vcard_addresses(config, terms, count, deadline)

        self.session.ui.mark('Searching Metadata')
        index_addrs = self._index_addresses(config, terms, vcard_addrs,
                                            count, deadline)

        self.session.ui.mark('Sorting')
        addresses = vcard_addrs + index_addrs
        addresses.sort(key=lambda k: -k['rank'])
        total = len(addresses)
        return self._success(_('Searched for addresses'), result={
            'addresses': addresses[offset:min(offset+count, total)],
            'displayed': min(count, total),
            'total': total,
            'offset': offset,
            'count': count,
            'start': offset,
            'end': offset+count,
        })


def ProfileVCard(parent):
    """A factory for generating profile commands"""
    synopsis = [(t and t.replace('vcard', 'profile') or t)
                for t in parent.SYNOPSIS]
    synopsis[2] = synopsis[1]

    class ProfileVCardCommand(parent):
        SYNOPSIS = tuple(synopsis)
        KIND = 'profile'
        ORDER = ('Tagging', 3)
        VCARD = "profile"

        DEFAULT_KEYTYPE = 'RSA3072'

        def _default_signature(self):
            return _('Sent using Mailpile, Free Software from www.mailpile.is')

        def _augment_list_info(self, info):
            info['default_sig'] = self._default_signature()
            return info

        def _yn(self, val, default='no'):
            return truthy(self.data.get(val, [default])[0])

        def _sendmail_command(self):
            # FIXME - figure out where sendmail is for reals
            return mailpile.config.defaults.DEFAULT_SENDMAIL

        def _sanity_check(self, kind, triplets):
            route_id = self.data.get('route_id', [None])[0]
            if (route_id or [k for k in self.data.keys() if k[:5] in
                             ('route', 'smtp-', 'sourc', 'secur', 'local')]):
                if len(triplets) > 1 or kind != 'profile':
                    raise ValueError('Can only configure detailed settings '
                                     'for one profile at a time')

            # FIXME: Check more important invariants and raise

        def _configure_sending_route(self, vcard, route_id):
            # Sending route
            route = self.session.config.routes.get(route_id)
            protocol = self.data.get('route-protocol', ['none'])[0]
            if protocol == 'none':
                if route:
                    del self.session.config.routes[route_id]
                vcard.route = ''
                return
            elif protocol == 'local':
                route.password = route.username = route.host = ''
                route.name = _("Local mail")
                route.command = self.data.get('route-command', [None]
                                              )[0] or self._sendmail_command()
            elif protocol in ('smtp', 'smtptls', 'smtpssl'):
                route.command = ''
                route.name = vcard.email
                for var in ('route-username', 'route-auth_type',
                            'route-host', 'route-port'):
                    rvar = var.split('-', 1)[1]
                    route[rvar] = self.data.get(var, [''])[0]
                if 'route-password' in self.data:
                    route['password'] = self.data['route-password'][0]
            else:
                raise ValueError(_('Unhandled outgoing mail protocol: %s'
                                   ) % protocol)
            route.protocol = protocol
            vcard.route = route_id

        def _get_mail_spool(self):
            path = os.getenv('MAIL') or None
            user = os.getenv('USER')
            if user and not path:
                if os.path.exists('/var/spool/mail'):
                    path = os.path.normpath('/var/spool/mail/%s' % user)
                if os.path.exists('/var/mail'):
                    path = os.path.normpath('/var/mail/%s' % user)
            return path

        def _configure_mail_sources(self, vcard):
            config = self.session.config
            sources = [r[7:].rsplit('-', 1)[0] for r in self.data.keys()
                       if r.startswith('source-') and r.endswith('-protocol')]
            for src_id in sources:
                prefix = 'source-%s-' % src_id
                protocol = self.data.get(prefix + 'protocol', ['none'])[0]
                def configure_source(source):
                    source.host = ''
                    source.username = ''
                    source.enabled = self._yn(prefix + 'enabled')
                    source.discovery.create_tag = True
                    source.discovery.process_new = True
                    if src_id not in vcard.sources():
                        vcard.add_source(source._key)
                    return source
                def make_new_source():
                    # This little dance makes sure source is actually a
                    # config section, not just an anonymous dict.
                    if src_id not in config.sources:
                        config.sources[src_id] = {}
                    source = config.sources[src_id]
                    source.profile = vcard.random_uid
                    source.discovery.apply_tags = [vcard.tag]
                    return configure_source(source)

                if protocol == 'none':
                    pass

                elif protocol == 'local':
                    source = configure_source(vcard.get_source_by_proto(
                        'local', create=src_id))

                elif protocol == 'spool':
                    path = self._get_mail_spool()
                    if not path:
                        raise ValueError(_('Mail spool not found'))

                    if path in config.sys.mailbox.values():
                        raise ValueError(_('Already configured: %s') % path)
                    else:
                        mailbox_idx = config.sys.mailbox.append(path)

                    source = configure_source(vcard.get_source_by_proto(
                        'local', create=src_id))
                    src_id = source._key

                    # We need to communicate with the source below,
                    # so we save config to trigger instanciation.
                    self._background_save(config=True, wait=True)

                    inbox = [t._key for t in config.get_tags(type='inbox')]
                    local_copy = self._yn(prefix + 'copy-local')
                    if self._yn(prefix + 'delete-source'):
                        policy = 'move'
                    else:
                        policy = 'read'

                    src_obj = config.mail_sources[src_id]
                    src_obj.take_over_mailbox(mailbox_idx,
                                              policy=policy,
                                              create_local=local_copy,
                                              apply_tags=inbox,
                                              save=False)

                elif protocol in ('imap', 'imap_ssl', 'imap_tls',
                                  'pop3', 'pop3_ssl'):
                    source = make_new_source()

                    # Discovery policy
                    disco = source.discovery
                    if self._yn(prefix + 'index-all-mail'):
                        if self._yn(prefix + 'leave-on-server'):
                            disco.policy = 'sync'
                        else:
                            disco.policy = 'move'
                        disco.local_copy = True
                        disco.paths = ['/']
                    else:
                        disco.policy = 'ignore'
                        disco.local_copy = False
                        disco.paths = []
                    disco.guess_tags = True

                    # Connection settings
                    for rvar in ('protocol', 'auth_type', 'username',
                                 'host', 'port'):
                        source[rvar] = self.data.get(prefix + rvar, [''])[0]
                    if (prefix + 'password') in self.data:
                        source['password'] = self.data[prefix + 'password'][0]
                    if (self._yn(prefix + 'force-starttls')
                            and source.protocol == 'imap'):
                        source.protocol = 'imap_tls'
                    username = source.username
                    if '@' not in username:
                        username += '@%s' % source.host
                    source.name = username

                    # We need to communicate with the source below,
                    # so we save config to trigger instanciation.
                    self._background_save(config=True, wait=True)
                    src_obj = config.mail_sources[src_id]

                else:
                    raise ValueError(_('Unhandled incoming mail protocol: %s'
                                       ) % protocol)

        def _new_key_created(self, event, vcard_rid, passphrase):
            config = self.session.config
            fingerprint = self._key_generator.generated_key
            if fingerprint:
                vcard = vcard_rid and config.vcards.get_vcard(vcard_rid)
                if vcard:
                    vcard.pgp_key = fingerprint
                    vcard.save()
                    event.message = _('The PGP key for %s is ready for use.'
                                      ) % vcard.email
                else:
                    event.message = _('PGP key generation is complete')

                # Record the passphrase!
                config.secrets[fingerprint] = {
                    'password': passphrase,
                    'policy': 'protect'}

                # FIXME: Toggle something that indicates we need a backup ASAP.
                self._background_save(config=True)
            else:
                event.message = _('PGP key generation failed!')
                event.data['keygen_failed'] = True

            event.flags = event.COMPLETE
            event.data['keygen_finished'] = int(time.time())
            config.event_log.log_event(event)

        def _create_new_key(self, vcard, keytype_arg):
            passphrase = generate_autocrypt_setup_code()
            random_uid = vcard.random_uid

            if keytype_arg[:3].upper() == 'RSA':
                keytype = GnuPGBaseKeyGenerator.KEYTYPE_RSA
                bits = int(keytype_arg[3:])
            elif keytype_arg.upper() in ('ECC', 'ED25519', 'CURVE25519'):
                keytype = GnuPGBaseKeyGenerator.KEYTYPE_CURVE25519
                bits = None
            else:
                raise ValueError('Unknown keytype: %s' % keytype_arg)

            key_args = {
                'keytype': keytype,
                'bits': bits,
                'name': vcard.fn,
                'email': vcard.email,
                'passphrase': passphrase,
                'comment': ''}
            event = Event(source=self,
                          flags=Event.INCOMPLETE,
                          data={'keygen_started': int(time.time()),
                                'profile_id': random_uid},
                          private_data=key_args)
            self._key_generator = GnuPGKeyGenerator(
               # FIXME: Passphrase handling is a problem here
               GnuPG(self.session.config, event=event),
               event=event,
               variables=dict_merge(GnuPGBaseKeyGenerator.VARIABLES, key_args),
               on_complete=(random_uid,
                            lambda: self._new_key_created(event, random_uid,
                                                          passphrase)))
            self._key_generator.start()
            self.session.config.event_log.log_event(event)

        def _configure_security(self, vcard):
            openpgp_key = self.data.get('security-pgp-key', [''])[0]
            if openpgp_key:
                if openpgp_key.startswith('!CREATE'):
                    key_type = openpgp_key[8:] or self.DEFAULT_KEYTYPE
                    self._create_new_key(vcard, key_type)
                else:
                    vcard.pgp_key = openpgp_key
                    # FIXME: Schedule a background sync job which edits
                    #        the key to add this Account as a UID, if it

            else:
                vcard.remove_all('key')

            # Set the following even if we don't have a key, so they don't
            # get lost if the user edits settings while a key is being
            # generated - or if they just deselect a key temporarily.

            # Encryption policy rules
            outg_auto = self._yn('security-best-effort-crypto')
            outg_sig  = self._yn('security-always-sign')
            outg_enc  = self._yn('security-always-encrypt')
            if outg_enc and outg_sig:
                vcard.crypto_policy = 'openpgp-sign-encrypt'
            elif outg_sig:
                vcard.crypto_policy = 'openpgp-sign'
            elif outg_enc:
                vcard.crypto_policy = 'openpgp-encrypt'
            elif outg_auto:
                vcard.crypto_policy = 'best-effort'
            else:
                vcard.crypto_policy = 'none'

            # Crypto formatting rules
            pgp_autocrypt    = self._yn('security-use-autocrypt')
            pgp_publish      = self._yn('security-publish-to-keyserver')
            pgp_keys         = self._yn('security-attach-keys')
            pgp_inline       = self._yn('security-prefer-inline')
            pgp_pgpmime      = self._yn('security-prefer-pgpmime')
            pgp_obscure_meta = self._yn('security-obscure-metadata')
            pgp_hdr_enc      = self._yn('security-openpgp-header-encrypt')
            pgp_hdr_sig      = self._yn('security-openpgp-header-sign')
            pgp_hdr_none     = self._yn('security-openpgp-header-none')
            pgp_hdr_both     = pgp_hdr_enc and pgp_hdr_sig
            if pgp_hdr_both:
                pgp_hdr_enc = pgp_hdr_sig = False
            if pgp_pgpmime and pgp_inline:
                pgp_pgpmime = pgp_inline = False
            vcard.crypto_format = ''.join([
                'openpgp_header:SE' if (pgp_hdr_both)     else '',
                'openpgp_header:S'  if (pgp_hdr_sig)      else '',
                'openpgp_header:E'  if (pgp_hdr_enc)      else '',
                'openpgp_header:N'  if (pgp_hdr_none)     else '',
                '+autocrypt'        if (pgp_autocrypt)    else '',
                '+send_keys'        if (pgp_keys)         else '',
                '+prefer_inline'    if (pgp_inline)       else '',
                '+pgpmime'          if (pgp_pgpmime)      else '',
                '+obscure_meta'     if (pgp_obscure_meta) else '',
                '+publish'          if (pgp_publish)      else ''
            ])

    return ProfileVCardCommand


class Profile(ProfileVCard(VCard)):
    """View profile"""


class AddProfile(ProfileVCard(AddVCard)):
    """Add profiles (Accounts)"""
    HTTP_POST_VARS = dict_merge(AddVCard.HTTP_POST_VARS, {
        'route_id': 'Route ID for sending mail',

        'signature': '.signature',
        'route-*': 'Route settings',
        'source-*': 'Source settings',
        'security-*': 'Security settings'
    })

    def _form_defaults(self):
        new_src_id = randomish_uid();
        return dict_merge(AddVCard._form_defaults(self), {
            'new_src_id': new_src_id,
            'signature': self._default_signature(),
            'route-protocol': 'none',
            'route-auth_type': 'password',
            'source-NEW-protocol': 'none',
            'source-NEW-auth_type': 'password',
            'source-NEW-leave-on-server': True,
            'source-NEW-index-all-mail': True,
            'source-NEW-force-starttls': False,
            'source-NEW-copy-local': True,
            'source-NEW-delete-source': False,
            'security-best-effort-crypto': True,
            'security-always-sign': False,
            'security-always-encrypt': False,
            'security-use-autocrypt': True,
            'security-attach-keys': False,
            'security-prefer-inline': False,
            'security-prefer-pgpmime': False,
            'security-obscure-metadata': False,
            'security-openpgp-header-encrypt': False,
            'security-openpgp-header-sign': True,
            'security-openpgp-header-none': False,
            'security-publish-to-keyserver': False
        });

    def _before_vcard_create(self, kind, triplets, vcard=None):
        route_id = self.data.get('route_id',
                                 [vcard and vcard.route or None])[0]
        if route_id:
            if route_id not in self.session.config.routes:
                raise ValueError('Not a valid route ID: %s' % route_id)
        elif self.data.get('route-protocol', ['none'])[0] != 'none':
            route_id = self.session.config.routes.append({})

        return {
            'save_config': True,
            'route_id': route_id
        }

    def _update_vcard_from_post(self, vcard, state=None):
        if not state:
            # When editing, this doesn't run first, so we invoke it now.
            state = self._before_vcard_create(vcard.kind, [], vcard=vcard)

        vcard.signature = self.data.get('signature', [''])[0]
        vcard.email = self.data.get('email', [None])[0] or vcard.email
        vcard.fn = self.data.get('name', [None])[0] or vcard.fn

        if not vcard.tag:
            with self.session.config._lock:
                tags = self.session.config.tags
                vcard.tag = tags.append({
                    'name': vcard.email,
                    'slug': '%8.8x' % time.time(),
                    'type': 'profile',
                    'icon': 'icon-user',
                    'flag_msg_only': True,
                    'label': False,
                    'display': 'invisible'
                })
                from mailpile.plugins.tags import Slugify
                tags[vcard.tag].slug = Slugify(
                    'account-%s' % vcard.email, tags=self.session.config.tags)

        route_id = state.get('route_id')
        if route_id:
            self._configure_sending_route(vcard, route_id)

        self._configure_mail_sources(vcard)
        self._configure_security(vcard)

    def _after_vcard_create(self, kind, vcard, state):
        self._update_vcard_from_post(vcard, state=state)


class EditProfile(AddProfile):
    """Edit a profile"""
    SYNOPSIS = (None, None, 'profiles/edit', None)
    HTTP_QUERY_VARS = dict_merge(AddProfile.HTTP_QUERY_VARS, {
        'rid': 'update by x-mailpile-rid'})

    def _vcard_to_post_vars(self, vcard):
        cp = vcard.crypto_policy or ''
        cf = vcard.crypto_format or ''
        vc_sig = vcard.signature
        default_sig = self._default_signature()
        pvars = {
            'rid': vcard.random_uid,
            'name': vcard.fn,
            'email': vcard.email,
            'signature': default_sig if (vc_sig is None) else vc_sig,
            'password': '',
            'route-protocol': 'none',
            'route-auth_type': 'password',
            'source-NEW-protocol': 'none',
            'source-NEW-auth_type': 'password',
            'security-pgp-key': vcard.pgp_key or '',
            'security-best-effort-crypto': ('best-effort' in cp),
            'security-use-autocrypt': ('autocrypt' in cf),
            'security-always-sign': ('sign' in cp),
            'security-always-encrypt': ('encrypt' in cp),
            'security-attach-keys': ('send_keys' in cf),
            'security-prefer-inline': ('prefer_inline' in cf),
            'security-prefer-pgpmime': ('pgpmime' in cf),
            'security-obscure-metadata': ('obscure_meta' in cf),
            'security-openpgp-header-encrypt': ('openpgp_header:E' in cf or
                                                'openpgp_header:SE' in cf),
            'security-openpgp-header-sign': ('openpgp_header:S' in cf or
                                             'openpgp_header:ES' in cf),
            'security-openpgp-header-none': ('openpgp_header:N' in cf),
            'security-publish-to-keyserver': ('publish' in cf)
        }
        route = self.session.config.routes.get(vcard.route or 'ha ha ha')
        if route:
            pvars.update({
                'route-protocol': route.protocol,
                'route-host': route.host,
                'route-port': route.port,
                'route-username': route.username,
                'route-password': route.password,
                'route-auth_type': route.auth_type or 'password',
                'route-command': route.command
            })
        pvars['sources'] = vcard.sources()
        for sid in pvars['sources']:
            prefix = 'source-%s-' % sid
            source = self.session.config.sources.get(sid)
            disco = source.discovery
            info = {}
            for rvar in ('protocol', 'auth_type', 'host', 'port',
                         'username', 'password'):
                info[prefix + rvar] = source[rvar]
            dp = disco.policy
            if not info[prefix + 'auth_type']:
                info[prefix + 'auth_type'] = 'password'
            info[prefix + 'leave-on-server'] = (dp not in 'move')
            info[prefix + 'index-all-mail'] = (dp in ('move', 'sync', 'read')
                                               and disco.local_copy)
            info[prefix + 'enabled'] = source.enabled
            if source.protocol == 'imap_tls':
                info[prefix + 'protocol'] = 'imap'
                info[prefix + 'force-starttls'] = True
            else:
                info[prefix + 'force-starttls'] = False

            pvars.update(info)
        return pvars

    def command(self):
        idx = self._idx()  # Make sure VCards are all loaded
        session, config = self.session, self.session.config

        # OK, fetch the VCard.
        safe_assert('rid' in self.data and len(self.data['rid']) == 1)
        vcard = config.vcards.get_vcard(self.data['rid'][0])
        safe_assert(vcard)

        if self.data.get('_method') == 'POST':
            self._update_vcard_from_post(vcard)
            self._background_save(config=True)
            vcard.save()
            return self._success(_('Account Updated!'),
                                 self._vcard_to_post_vars(vcard))
        else:
            return self._success(_('Edit Account'), dict_merge(
                 self._form_defaults(), self._vcard_to_post_vars(vcard)))


class RemoveProfile(ProfileVCard(RemoveVCard)):
    """Remove a profile"""
    HTTP_CALLABLE = ('GET', 'POST')
    HTTP_QUERY_VARS = dict_merge(RemoveVCard.HTTP_QUERY_VARS, {
        'rid': 'x-mailpile-rid of profile to remove'})
    HTTP_POST_VARS = {
        'rid': 'x-mailpile-rid of profile to remove',
        'trash-email': 'If yes, move linked e-mail to Trash',
        'delete-keys': 'If yes, delete linked PGP keys',
        'delete-tags': 'If yes, remove linked Tags'}

    def _trash_email(self, vcard):
        trashes = self.session.config.get_tags(type='trash', default=[])
        if vcard.tag and trashes:
            idx = self.session.config.index
            idx.add_tag(self.session, trashes[0]._key,
                        msg_idxs=idx.TAGS.get(vcard.tag, set()),
                        allow_message_id_clearing=True,
                        conversation=False)

    def _delete_keys(self, vcard):
        if vcard.pgp_key:
            found = 0
            for vc in self.session.config.vcards.find_vcards([], kinds=['profile']):
                if vc.pgp_key == vcard.pgp_key:
                    found += 1
            if found == 1:
                self._gnupg().delete_key(vcard.pgp_key)

    def _cleanup_tags(self, vcard, delete_tags=False):
        if vcard.tag:
            if delete_tags:
                from mailpile.plugins.tags import DeleteTag
                DeleteTag(self.session, arg=[vcard.tag]).run()
            else:
                self.session.config.tags[vcard.tag].type = 'attribute'
                self.session.config.tags[vcard.tag].display = 'invisible'
                self.session.config.tags[vcard.tag].label = True

    def _unique_usernames(self, vcard):
        config, usernames = self.session.config, set()

        if (vcard.route not in ('', None)) and config.routes[vcard.route].username:
            usernames.add(config.routes[vcard.route].username)
        for source_id in vcard.sources():
            if config.sources[source_id].username:
                usernames.add(config.sources[source_id].username)

        for msid, source in config.sources.iteritems():
            if (source.username in usernames) and (source.profile != vcard.random_uid):
                usernames.remove(source.username)
        for mrid, route in config.routes.iteritems():
            if (route.username in usernames) and (mrid != vcard.route):
                usernames.remove(source.username)

        return usernames

    def _delete_credentials(self, vcard):
        # Check every stored credential; if it is in use by any route or source that
        # doesn't belong to this VCard, leave intact. Otherwise, delete.
        usernames = self._unique_usernames(vcard)
        oauth_tks = self.session.config.oauth.tokens
        for username in (set(oauth_tks.keys()) & usernames):
            del oauth_tks[username]
        secrets = self.session.config.secrets
        for username in (set(secrets.keys()) & usernames):
            del secrets[username]

    def _delete_routes(self, vcard):
        if vcard.route not in (None, ''):
            found = 0
            for vc in self.session.config.vcards.find_vcards([], kinds=['profile']):
                if vc.route == vcard.route:
                    found += 1
            if found == 1:
                self.session.config.routes[vcard.route] = {}

    def _delete_sources(self, vcard, delete_tags=False):
        config, sources = self.session.config, self.session.config.sources
        for source_id in vcard.sources():
            src = sources[source_id]
            tids = set()

            # Tell the worker to shut down, if any
            if source_id in config.mail_sources:
                config.mail_sources[source_id].quit()
                config.mail_sources[source_id].event.flags = Event.COMPLETE

            # Keep the reference to our local mailboxes in sys.mailbox
            for mbx_id, mbx_info in src.mailbox.iteritems():
                if mbx_info.primary_tag:
                    tids.add(mbx_info.primary_tag)
                if mbx_info.local and (mbx_info.path[:1] == '@'):
                    config.sys.mailbox[mbx_info.path[1:]] = mbx_info.local

            # Reconfigure all the tags
            from mailpile.plugins.tags import DeleteTag
            if src.discovery.parent_tag:
                tids.add(src.discovery.parent_tag)
            for tid in tids:
                if ((tid in config.tags)
                        and config.tags[tid].type in ('mailbox', 'profile')):
                    config.tags[tid].type = 'tag'
                    if delete_tags:
                        DeleteTag(self.session, arg=[tid]).run()

            # Nuke it!
            sources[source_id] = {
                'name': 'Deleted source',
                'enabled': False}

    def _trash_email_is_safe(self, vcard):
        if vcard:
            for src_id in vcard.sources():
                if self.session.config.sources[src_id].protocol == 'local':
                    return False
            return True
        return False

    def command(self, *args, **kwargs):
        session, config = self.session, self.session.config

        if 'rid' in self.data:
            vcard = config.vcards.get_vcard(self.data['rid'][0])
        else:
            vcard = None

        if vcard and self.data.get('_method', 'not-http').upper() != 'GET':
            if self.data.get('trash-email', [''])[0].lower() == 'yes':
                self._trash_email(vcard)

            if self.data.get('delete-keys', [''])[0].lower() == 'yes':
                self._delete_keys(vcard)

            delete_tags = (self.data.get('delete-tags', [''])[0].lower() == 'yes')
            self._delete_credentials(vcard)
            self._delete_routes(vcard)
            self._delete_sources(vcard, delete_tags=delete_tags)
            self._cleanup_tags(vcard, delete_tags=delete_tags)
            self._background_save(config=True, index=True)

            return RemoveVCard.command(self, *args, **kwargs)

        return self._success(_("Remove account"), result=dict_merge(
            self._form_defaults(), {
                'rid': vcard.random_uid if vcard else None,
                'trash_email_is_safe': self._trash_email_is_safe(vcard),
                'profile': (self._vcard_list([vcard])['profiles'][0]
                            if vcard else None)}))


class ListProfiles(ProfileVCard(ListVCards)):
    """Find profiles"""
    SYNOPSIS = (None, 'profiles', 'profiles', '[--lines] [<terms>]')


class ProfileSet(ProfileVCard(VCardSet)):
    """Set contact lines, ensuring contact exists"""


class ChooseFromAddress(Command):
    """Display a single vcard"""
    SYNOPSIS = (None, 'profiles/choose_from', 'profiles/choose_from',
                '<MIDs or addresses>')
    ORDER = ('Internals', 6)
    HTTP_CALLABLE = ('GET',)
    HTTP_QUERY_VARS = {
        'mid': 'Message ID',
        'email': 'E-mail address',
        'no_from': 'Ignore From: lines'
    }

    def command(self):
        idx, vcards = self._idx(), self.session.config.vcards

        emails = [e for e in self.args if '@' in e]
        emails.extend(self.data.get('email', []))

        messages = self._choose_messages(
            [m for m in self.args if '@' not in m] +
            ['=%s' % mid for mid in self.data.get('mid', [])]
        )
        for msg_idx_pos in messages:
            try:
                msg_info = idx.get_msg_at_idx_pos(msg_idx_pos)
                msg_emails = (idx.expand_to_list(msg_info, field=idx.MSG_TO) +
                              idx.expand_to_list(msg_info, field=idx.MSG_CC))
                emails.extend(msg_emails)
                if 'no_from' not in self.data:
                    emails.append(msg_info[idx.MSG_FROM])
            except ValueError:
                pass

        addrs = [ai for ee in emails
                 for ai in AddressHeaderParser(unicode_data=ee)]
        return self._success(_('Choosing from address'), result={
            'emails': addrs,
            'from': vcards.choose_from_address(self.session.config, addrs)
        })


class ContentTxf(EmailTransform):
    def TransformOutgoing(self, sender, rcpts, msg, **kwargs):
        txf_matched, txf_continue = False, True

        profile = self._get_sender_profile(sender, kwargs)
        sig = profile.get('signature')
        if sig:
            part = self._get_first_part(msg, 'text/plain')
            if part is not None:
                msg_text = (part.get_payload(decode=True) or '\n\n'
                            ).replace('\r', '').decode('utf-8')
                if '\n-- \n' not in msg_text:
                    msg_text = msg_text.strip() + '\n\n-- \n' + sig
                    try:
                        msg_text.encode('us-ascii')
                        need_utf8 = False
                    except (UnicodeEncodeError, UnicodeDecodeError):
                        msg_text = msg_text.encode('utf-8')
                        need_utf8 = True

                    part.set_payload(msg_text)
                    if need_utf8:
                        part.set_charset('utf-8')
                        while 'content-transfer-encoding' in part:
                            del part['content-transfer-encoding']
                        encoders.encode_base64(part)

                    txf_matched = True

        return sender, rcpts, msg, txf_matched, txf_continue


_plugins.register_commands(VCard, AddVCard, RemoveVCard, ListVCards,
                           VCardAddLines, VCardSet, VCardRemoveLines)
_plugins.register_commands(Contact, AddContact, RemoveContact, ListContacts,
                           ContactSet, AddressSearch)
_plugins.register_commands(Profile, AddProfile, EditProfile,
                           RemoveProfile, ListProfiles, ProfileSet,
                           ChooseFromAddress)
_plugins.register_commands(ContactImport, ContactImporters)

_plugins.register_outgoing_email_content_transform('100_sender_vc', ContentTxf)
