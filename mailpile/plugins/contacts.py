import mailpile.plugins
from mailpile.commands import Command, Action
from mailpile.mailutils import Email, ExtractEmails
from mailpile.vcard import SimpleVCard, VCardLine
from mailpile.util import *


class ContactImporter:
    required_parameters = []
    optional_parameters = []
    format_name = ""

    def __init__(self, **kwargs):
        self.args = kwargs

    def load(self):
        pass

    def get_contacts(self):
        return []

    def filter_contacts(self, terms):
        # We put this in each ContactImporter because sometimes fetching
        # everything and then filtering might be really slow, and in those
        # cases there might be a faster way. Example: CardDAV lookup.
        return []


class ContactExporter:
    required_parameters = []
    optional_parameters = []
    format_name = ""

    def __init__(self):
        self.exporting = []

    def add_contact(self, contact):
        self.exporting.append(contact)

    def remove_contact(self, contact):
        self.exporting.remove(contact)

    def save(self):
        pass


class ContactContextProvider:
    provider_name = ""

    def __init__(self, contact):
        self.contact = contact

    def get_recent_context(self, max=10):
        pass

    def get_related_context(self, query, max=10):
        pass


class ContactFieldValidator:
    def __init__(self):
        pass


##[ Pluggable contact management ]########################################

CONTACT_IMPORTERS = {}
CONTACT_EXPORTERS = {}
CONTACT_FIELD_VALIDATORS = {}
CONTACT_CONTEXT_PROVIDERS = {}


def register_contact_importer(importer):
    if not issubclass(importer, ContactImporter):
        raise PluginError("Plugin must be a ContactImporter")
    if importer.format_name in CONTACT_IMPORTERS.keys():
        raise PluginError("Importer for %s already registered"
                          % importer.format_name)
    CONTACT_IMPORTERS[importer.short_name] = importer


def register_contact_exporter(exporter):
    if not issubclass(importer, ContactExporter):
        raise PluginError("Plugin must be a ContactExporter")
    if exporter.format_name in CONTACT_EXPORTERS.keys():
        raise PluginError("Exporter for %s already registered"
                          % exporter.format_name)
    CONTACT_EXPORTERS[exporter.short_name] = exporter


def register_contact_field_validator(field, validator):
    if not issubclass(importer, ContactFieldValidator):
        raise PluginError("Plugin must be a ContactFieldValidator")
    if field in CONTACT_FIELD_VALIDATORS.keys():
        raise PluginError("Field validator for field %s already registered"
                          % field)
    CONTACT_FIELD_VALIDATORS[field] = validator


def register_contact_context_provider(provider):
    if not issubclass(importer, ContactContextProvider):
        raise PluginError("Plugin must be a ContactContextProvider")
    if importer.provider_name in CONTACT_CONTEXT_PROVIDERS.keys():
        raise PluginError("Context provider for %s already registered"
                          % provider.provider_name)
    CONTACT_CONTEXT_PROVIDERS[provider.provider_name] = provider


##[ VCards ]########################################

class VCardCommand(Command):
    VCARD = "vcard"

    def _fparse(self, fromdata):
        email = ExtractEmails(fromdata)[0]
        name = fromdata.replace(email, '').replace('<>', '').strip()
        return email, (name or email)

    def _make_new_vcard(self, handle, name):
        l = [VCardLine(name='fn', value=name),
             VCardLine(name='kind', value=self.KIND)]
        if self.KIND == 'individual':
            return SimpleVCard(VCardLine(name='email', value=handle), *l)
        else:
            return SimpleVCard(VCardLine(name='nickname', value=handle), *l)

    def _valid_vcard_handle(self, vc_handle):
        return (vc_handle and '@' in vc_handle[1:])

    def _add_from_messages(self):
        pairs, idx = [], self._idx()
        for email in [Email(idx, i) for i in self._choose_messages(self.args)]:
            pairs.append(self._fparse(email.get_msg_info(idx.MSG_FROM)))
        return pairs

    def _pre_delete_vcard(self, vcard):
        pass

    def _vcard_list(self, vcards, mode='mpCard', info=None):
        info = info or {}
        if mode == 'lines':
            data = [x.as_lines() for x in vcards]
        else:
            data = [x.as_mpCard() for x in vcards]
        info.update({
            self.VCARD+'s': data,
            "count": len(vcards)
        })
        return info


class VCard(VCardCommand):
    """Add/remove/list/edit vcards"""
    SYNOPSIS = (None, 'vcard', None, '<nickname>')
    ORDER = ('Internals', 6)
    KIND = ''

    def command(self, save=True):
        session, config = self.session, self.session.config
        vcards = []
        for email in self.args:
            vcard = config.vcards.get_vcard(email)
            if vcard:
                vcards.append(vcard)
            else:
                session.ui.warning('No such %s: %s' % (self.VCARD, email))
        return vcards


class AddVCard(VCardCommand):
    """Add one or more vcards"""
    SYNOPSIS = (None, 'vcard/add', None, '<msgs>', '<email> = <name>')
    ORDER = ('Internals', 6)
    KIND = ''
    HTTP_CALLABLE = ('POST', 'PUT')

    def command(self):
        session, config, idx = self.session, self.session.config, self._idx()

        if (len(self.args) > 2
        and self.args[1] == '='
        and self._valid_vcard_handle(self.args[0])):
            pairs = [(self.args[0], ' '.join(self.args[2:]))]
        elif self.data:
            if "@contactname" in self.data and "@contactemail" in self.data:
                pairs = [(self.data["@contactemail"],
                          self.data["@contactname"])]
            elif "contactnames" in self.data and "contactemails" in self.data:
                pairs = zip(self.data["contactemails"],
                            self.data["contactnames"])
        else:
            pairs = self._add_from_messages()

        if pairs:
            vcards = []
            for handle, name in pairs:
                if handle.lower() not in config.vcards:
                    vcard = self._make_new_vcard(handle, name)
                    config.vcards.add_vcard(vcard)
                    vcards.append(vcard)
                else:
                    session.ui.warning('Already exists: %s' % handle)
        else:
            return self._error('Nothing to do!')
        return {"contacts": [x.as_mpCard() for x in vcards]}


class VCardAddLines(VCardCommand):
    """Add a lines to a VCard"""
    SYNOPSIS = (None, 'vcard/addline', None, '<email> <lines>')
    ORDER = ('Internals', 6)
    KIND = ''
    HTTP_CALLABLE = ('POST', 'UPDATE')

    def command(self):
        session, config = self.session, self.session.config
        handle, var, lines = self.args[0], self.args[1], self.args[2:]
        vcard = config.vcards.get_vcard(handle)
        if not vcard:
            return self._error('%s not found: %s' % (self.VCARD, handle))
        config.vcards.deindex_vcard(vcard)
        try:
            vcard.add(*[VCardLine(l) for l in lines])
            vcard.save()
            return self._vcard_list([vcard], info={
                'updated': handle,
                'added': len(lines)
            })
        except:
            config.vcards.index_vcard(vcard)
            self._ignore_exception()
            return self._error('Error setting %s = %s' % (var, val))
        finally:
            config.vcards.index_vcard(vcard)


class RemoveVCard(VCardCommand):
    """Delete vcards"""
    SYNOPSIS = (None, 'vcard/remove', None, '<email>')
    ORDER = ('Internals', 6)
    KIND = ''
    HTTP_CALLABLE = ('POST', 'DELETE')

    def command(self):
        session, config = self.session, self.session.config
        for handle in self.args:
            vcard = config.vcards.get_vcard(handle)
            if vcard:
                self._pre_delete_vcard(vcard)
                config.vcards.del_vcard(handle)
            else:
                session.ui.error('No such contact: %s' % handle)
        return True


class ListVCards(VCardCommand):
    """Find vcards"""
    SYNOPSIS = (None, 'vcard/list', None, '[--lines] [<terms>]')
    ORDER = ('Internals', 6)
    KIND = ''
    HTTP_QUERY_VARS = {
        'q': 'search terms',
        'format': 'lines or mpCard (default)'
    }

    def command(self):
        session, config = self.session, self.session.config
        kinds = self.KIND and [self.KIND] or []

        if 'format' in self.data:
            fmt = self.data['format'][0]
        elif self.args and self.args[0] == '--lines':
            self.args.pop(0)
            fmt = 'lines'
        else:
            fmt = 'mpCard'

        if 'q' in self.data:
            terms = self.data['q']
        else:
            terms = self.args

        vcards = config.vcards.find_vcards(terms, kinds=kinds)
        return self._vcard_list(vcards, mode=fmt, info={
            'terms': self.args
        })


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


class AddContact(ContactVCard(AddVCard)):
    """Add contacts"""


class ContactAddLines(ContactVCard(VCardAddLines)):
    """Set contact variables"""


class RemoveContact(ContactVCard(RemoveVCard)):
    """Remove a contact"""


class ListContacts(ContactVCard(ListVCards)):
    SYNOPSIS = (None, 'contact/list', 'contact/list', '[--lines] [<terms>]')
    """Find contacts"""


class ContactImport(Command):
    """Import contacts"""
    SYNOPSIS = (None, 'contact/import', 'contact/import', '[<parameters>]')
    ORDER = ('Internals', 6)
    HTTP_CALLABLE = ('GET', )

    def command(self, format, terms=None, **kwargs):
        session, config = self.session, self.session.config

        if not format in mailpile.plugins.CONTACT_IMPORTERS.keys():
            session.ui.error("No such import format")
            return False

        importer = mailpile.plugins.CONTACT_IMPORTERS[format]

        if not all([x in kwargs.keys() for x in importer.required_parameters]):
            session.ui.error("Required paramter missing. Required parameters "
                + "are: %s" % ", ".join(importer.required_parameters))
            return False

        allparams = importer.required_parameters + importer.optional_parameters

        if not all([x in allparams for x in kwargs.keys()]):
            session.ui.error("Unknown parameter passed to importer."
                + " Provided %s; but known parameters are: %s"
                % (", ".join(kwargs), ", ".join(allparams)))
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
    SYNOPSIS = (None, 'contact/importers', 'contact/importers', '')
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
    }

    def _boost_rank(self, term, *matches):
        boost = 0.0
        for match in matches:
            match = match.lower()
            if term in match:
                if match.startswith(term):
                    boost += 25*(float(len(term)) / len(match))
                else:
                    boost += 5*(float(len(term)) / len(match))
        return int(boost)

    def _vcard_addresses(self, cfg, terms):
        addresses = []
        for vcard in cfg.vcards.find_vcards(terms, kinds='individual'):
             fn = vcard.get('fn')
             keys = [{'fingerprint': k.value, 'type': 'openpgp'}
                     for k in vcard.get_all('openpgp-key')]
             photos = vcard.get_all('photo')
             for email_vcl in vcard.get_all('email'):
                 rank = 10.0 + 25*len(keys) + 5*len(photos)
                 for term in terms:
                     rank += self._boost_rank(term, fn.value, email_vcl.value)
                 info = {
                     'rank': int(rank),
                     'fn': fn.value,
                     'proto': 'smtp',
                     'address': email_vcl.value,
                 }
                 if keys:
                     info['keys'] = [k for k in keys[:1]]
                 addresses.append(info)
        return addresses

    def _index_addresses(self, cfg, terms, vcard_addresses):
        existing = dict([(k['address'].lower(), k) for k in vcard_addresses])
        index = self._idx()

        # 1st, go through the last 1000 or so messages in the index and search
        # for matching senders or recipients, give medium priority.
        matches = {}
        addresses = []
        for msg_idx in range(0, len(index.INDEX))[-1000:]:
            frm = index.get_msg_at_idx_pos(msg_idx)[index.MSG_FROM]
            match = True
            for term in terms:
                if term not in frm.lower():
                    match = False
            if match:
                matches[frm] = matches.get(frm, 0) + 1
        for frm in matches:
            email, fn = self._fparse(frm)
            boost = min(10, matches[frm])
            for term in terms:
                boost += self._boost_rank(term, fn, email)

            if email.lower() in existing:
                 existing[email.lower()]['rank'] += min(20, boost)
            else:
                 info = {
                     'rank': boost,
                     'fn': fn,
                     'proto': 'smtp',
                     'address': email,
                 }
                 existing[email.lower()] = info
                 addresses.append(info)

        # FIXME: 2nd, search the social graph for matches, give low priority.

        return addresses

    def command(self):
        session, config = self.session, self.session.config
        if 'q' in self.data:
            terms = [t.lower() for t in self.data['q']]
        else:
            terms = [t.lower() for t in self.args]

        vcard_addrs = self._vcard_addresses(config, terms)
        index_addrs = self._index_addresses(config, terms, vcard_addrs)
        addresses = vcard_addrs + index_addrs
        addresses.sort(key=lambda k: -k['rank'])
        return {
            'addresses': addresses[:10]
        }


mailpile.plugins.register_commands(VCard, AddVCard, VCardAddLines,
                                   RemoveVCard, ListVCards)
mailpile.plugins.register_commands(Contact, AddContact, ContactAddLines,
                                   RemoveContact, ListContacts,
                                   AddressSearch)
mailpile.plugins.register_commands(ContactImport, ContactImporters)
