import mailpile.plugins
from mailpile.commands import Command, Action
from mailpile.mailutils import Email, ExtractEmails, ExtractEmailAndName
from mailpile.vcard import SimpleVCard, VCardLine
from mailpile.util import *


##[ VCards ]########################################

class VCardCommand(Command):
    VCARD = "vcard"

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
            pairs.append(ExtractEmailAndName(email.get_msg_info(idx.MSG_FROM)))
        return pairs

    def _pre_delete_vcard(self, vcard):
        pass

    def _vcard_list(self, vcards, mode='mpCard', info=None):
        info = info or {}
        if mode == 'lines':
            data = [x.as_lines() for x in vcards if x]
        else:
            data = [x.as_mpCard() for x in vcards if x]
        info.update({
            self.VCARD + 's': data,
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
        if len(vcards) == 1:
            return {"contact": vcards[0].as_mpCard()}
        else:
            return {"contacts": [x.as_mpCard() for x in vcards]}


class AddVCard(VCardCommand):
    """Add one or more vcards"""
    SYNOPSIS = (None, 'vcard/add', None, '<msgs>', '<email> = <name>')
    ORDER = ('Internals', 6)
    KIND = ''
    HTTP_CALLABLE = ('POST', 'PUT', 'GET')

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
        'format': 'lines or mpCard (default)',
        'count': 'how many to display (default=40)',
        'offset': 'skip how many in the display (default=0)',
    }
    HTTP_CALLABLE = ('GET')

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

        if 'count' in self.data:
            count = int(self.data['count'][0])
        else:
            count = 120

        if 'offset' in self.data:
            offset = int(self.data['offset'][0])
        else:
            offset = 0

        vcards = config.vcards.find_vcards(terms, kinds=kinds)
        total = len(vcards)
        vcards = vcards[offset:offset + count]
        return self._vcard_list(vcards, mode=fmt, info={
            'terms': self.args,
            'offset': offset,
            'count': count,
            'total': total,
            'start': offset,
            'end': offset + count,
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
    SYNOPSIS = (None, 'contact', 'contact', '[<email>]')

    def command(self, save=True):
        contact = VCard.command(self, save)
        # Tee-hee, monkeypatching results.
        contact["sent_messages"] = 0
        contact["received_messages"] = 0
        contact["last_contact_from"] = 10000000000000
        contact["last_contact_to"] = 10000000000000

        try:
            for email in contact["contact"]["email"]:
                s = Action(self.session, "search", ["in:Sent", "to:%s" % (email["email"])]).as_dict()
                print "TO: ", s
                contact["sent_messages"] += s["result"]["total"]
                for msg in s["result"]["messages"]:
                    if msg["timestamp"] < contact["last_contact_to"]:
                        contact["last_contact_to"] = msg["timestamp"]
                        contact["last_contact_to_msg_url"] = msg["url"]

                s = Action(self.session, "search", ["from:%s" % (email["email"])]).as_dict()
                print "FROM: ", s
                contact["received_messages"] += s["result"]["total"]
                for msg in s["result"]["messages"]:
                    if msg["timestamp"] < contact["last_contact_from"]:
                        contact["last_contact_from"] = msg["timestamp"]
                        contact["last_contact_from_msg_url"] = msg["url"]
        except Exception, e:
            print "ERROR:", e

        if contact["last_contact_to"] == 10000000000000:
            contact["last_contact_to"] = False
            contact["last_contact_to_msg_url"] = ""

        if contact["last_contact_from"] == 10000000000000:
            contact["last_contact_from"] = False
            contact["last_contact_from_msg_url"] = ""

        return contact

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
        'count': 'number of results',
        'offset': 'offset results'
    }

    def _boost_rank(self, term, *matches):
        boost = 0.0
        for match in matches:
            match = match.lower()
            if term in match:
                if match.startswith(term):
                    boost += 25 * (float(len(term)) / len(match))
                else:
                    boost += 5 * (float(len(term)) / len(match))
        return int(boost)

    def _vcard_addresses(self, cfg, terms):
        addresses = {}
        for vcard in cfg.vcards.find_vcards(terms, kinds='individual'):
            fn = vcard.get('fn')
            keys = []
            for k in vcard.get_all('KEY'):
                val = k.value.split("data:")[1]
                mime, fp = val.split(",")
                keys.append({'fingerprint': fp, 'type': 'openpgp',
                             'mime': mime})

            photos = vcard.get_all('photo')
            for email_vcl in vcard.get_all('email'):
                info = addresses.get(email_vcl.value)
                if not info:
                    info = {
                        'rank': 0,
                        'fn': fn.value,
                        'protocol': 'smtp',
                        'address': email_vcl.value,
                        'secure': False
                    }
                addresses[email_vcl.value] = info

                rank = 10.0 + 25 * len(keys) + 5 * len(photos)
                for term in terms:
                    rank += self._boost_rank(term, fn.value, email_vcl.value)
                info['rank'] += int(rank)

                if photos and 'photos' not in info:
                    info['photo'] = photos[0].value

                if keys and 'keys' not in info:
                    info['keys'] = [k for k in keys[:1]]
                    info['secure'] = True

        return addresses.values()

    def _index_addresses(self, cfg, terms, vcard_addresses):
        existing = dict([(k['address'].lower(), k) for k in vcard_addresses])
        index = self._idx()

        # Figure out which tags are invisible so we can skip messages marked
        # with those tags.
        invisible = set([t._key for t in cfg.get_tags(flag_hides=True)])

        # 1st, go through the last 1000 or so messages in the index and search
        # for matching senders or recipients, give medium priority.
        matches = {}
        addresses = []
        for msg_idx in index.INDEX_SORT['date_fwd'][-2500:]:
            msg_info = index.get_msg_at_idx_pos(msg_idx)
            tags = set(msg_info[index.MSG_TAGS].split(','))
            frm = msg_info[index.MSG_FROM]
            match = not (tags & invisible)
            if match:
                for term in terms:
                    if term not in frm.lower():
                        match = False
            if match:
                matches[frm] = matches.get(frm, 0) + 1
            if len(matches) > 1000:
                break

        # FIXME: 2nd, search the social graph for matches, give low priority.
        for frm in index.EMAILS:
            match = True
            for term in terms:
                if term not in frm.lower():
                    match = False
            if match:
                matches[frm] = matches.get(frm, 0) + 1

        # Assign info & scores!
        for frm in matches:
            email, fn = ExtractEmailAndName(frm)

            boost = min(10, matches[frm])
            for term in terms:
                boost += self._boost_rank(term, fn, email)

            if not email or '@' not in email:
                # FIXME: This may not be the right thing for alternate
                #        message transports.
                pass
            elif email.lower() in existing:
                existing[email.lower()]['rank'] += min(20, boost)
            else:
                info = {
                    'rank': boost,
                    'fn': fn,
                    'proto': 'smtp',
                    'address': email,
                    'secure': False
                }
                existing[email.lower()] = info
                addresses.append(info)

        return addresses

    def command(self):
        session, config = self.session, self.session.config
        if 'q' in self.data:
            terms = [t.lower() for t in self.data['q']]
        else:
            terms = [t.lower() for t in self.args]
        count = int(self.data.get('count', 10))
        offset = int(self.data.get('offset', 0))

        vcard_addrs = self._vcard_addresses(config, terms)
        index_addrs = self._index_addresses(config, terms, vcard_addrs)
        addresses = vcard_addrs + index_addrs
        addresses.sort(key=lambda k: -k['rank'])
        total = len(addresses)
        return {
            'addresses': addresses[offset:min(offset+count, total)],
            'displayed': min(count, total),
            'total': total,
            'offset': offset,
            'count': count,
            'start': offset,
            'end': offset+count,
        }


mailpile.plugins.register_commands(VCard, AddVCard, VCardAddLines,
                                   RemoveVCard, ListVCards)
mailpile.plugins.register_commands(Contact, AddContact, ContactAddLines,
                                   RemoveContact, ListContacts,
                                   AddressSearch)
mailpile.plugins.register_commands(ContactImport, ContactImporters)
