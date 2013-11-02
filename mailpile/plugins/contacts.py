import mailpile.plugins
from mailpile.commands import Command, Action
from mailpile.mailutils import Email, ExtractEmails
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

    def _prepare_new_vcard(self, vcard):
        pass

    def _valid_vcard_handle(self, vc_handle):
        return (vc_handle and '@' in vc_handle[1:])

    def _add_from_messages(self):
        pairs, idx = [], self._idx()
        for email in [Email(idx, i) for i in self._choose_messages(self.args)]:
            pairs.append(self._fparse(email.get_msg_info(idx.MSG_FROM)))
        return pairs

    def _pre_delete_vcard(self, vcard):
        pass

    def _format_values(self, key, vals):
        if key.upper() in ('MEMBER', ):
            return [['mailto:%s' % e, []] for e in vals]
        else:
            return [[e, []] for e in vals]


class VCard(VCardCommand):
    """Add/remove/list/edit vcards"""
    SYNOPSIS = (None, 'vcard', None, '<nickname>')
    ORDER = ('Internals', 6)
    KIND = ''

    def command(self, save=True):
        session, config = self.session, self.session.config
        vcards = []
        for email in self.args:
            vcard = config.get_vcard(email)
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
                    vcard = config.add_vcard(handle, name, self.KIND)
                    self._prepare_new_vcard(vcard)
                    vcards.append(vcard)
                else:
                    session.ui.warning('Already exists: %s' % handle)
        else:
            return self._error('Nothing to do!')
        return {"contacts": [x.as_mpCard() for x in vcards]}


class SetVCard(VCardCommand):
    """Set vcard variables"""
    SYNOPSIS = (None, 'vcard/set', None, '<email> <attr> <value>')
    ORDER = ('Internals', 6)
    KIND = ''
    HTTP_CALLABLE = ('POST', 'UPDATE')

    def command(self):
        session, config = self.session, self.session.config
        handle, var = self.args[0], self.args[1]
        if self.args[2] == '=':
            val = ' '.join(self.args[3:])
        else:
            val = ' '.join(self.args[2:])
        try:
            vcard = config.get_vcard(handle)
            if not vcard:
                return self._error('Contact not found')
            config.deindex_vcard(vcard)
            if val:
                if ',' in val:
                    vcard[var] = self._format_values(var, val.split(','))
                else:
                    vcard[var] = val
            else:
                del vcard[var]
            vcard.save()
            config.index_vcard(vcard)
            session.ui.display_vcard(vcard, compact=False)
            return True
        except:
            self._ignore_exception()
            return self._error('Error setting %s = %s' % (var, val))


class RemoveVCard(VCardCommand):
    """Delete vcards"""
    SYNOPSIS = (None, 'vcard/remove', None, '<email>')
    ORDER = ('Internals', 6)
    KIND = ''
    HTTP_CALLABLE = ('POST', 'DELETE')

    def command(self):
        session, config = self.session, self.session.config
        for handle in self.args:
            vcard = config.get_vcard(handle)
            if vcard:
                self._pre_delete_vcard(vcard)
                config.del_vcard(handle)
            else:
                session.ui.error('No such contact: %s' % handle)
        return True


class ListVCards(VCardCommand):
    """Find vcards"""
    SYNOPSIS = (None, 'vcard/list', None, '[--full] [<terms>]')
    ORDER = ('Internals', 6)
    KIND = ''

    def command(self):
        session, config = self.session, self.session.config
        if self.args and self.args[0] == '--full':
            self.args.pop(0)
            compact = False
        else:
            compact = True
        kinds = self.KIND and [self.KIND] or []
        vcards = config.find_vcards(self.args, kinds=kinds)
        #for vcard in vcards:
        #    session.ui.display_vcard(vcard, compact=compact)
        ctx = {}
        ctx[self.VCARD+'s'] = [x.as_mpCard() for x in vcards]
        ctx["query"] = " ".join(self.args)
        ctx["total"] = len(vcards)
        ctx["start"] = 1
        ctx["end"] = len(vcards)
        ctx["count"] = len(vcards)
        return ctx


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


class SetContact(ContactVCard(SetVCard)):
    """Set contact variables"""


class RemoveContact(ContactVCard(RemoveVCard)):
    """Remove a contact"""


class ListContacts(ContactVCard(ListVCards)):
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


mailpile.plugins.register_commands(VCard, AddVCard, SetVCard,
                                   RemoveVCard, ListVCards)
mailpile.plugins.register_commands(Contact, AddContact, SetContact,
                                   RemoveContact, ListContacts)
mailpile.plugins.register_commands(ContactImport, ContactImporters)
