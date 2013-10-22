import mailpile.plugins
from mailpile.commands import Command
from mailpile.util import *

from mailpile.gpgi import * 

# Old: Keeping this around for posterity, may be useful again...
#
# def import_vcards(self):
#     session, config, arg = self.session, self.session.config, self.args[0]
#     keys = self.filter()
#     vcards = []
#     for k in keys:
#         for uid in k["uids"]:
#             name, handle = uid.split(" <")
#             handle = handle.strip(">")
#             if handle.lower() not in config.vcards:
#                 vcard = config.add_vcard(handle, name, 'individual')
#                 vcard["KEY"] = [["data:application/x-pgp-fingerprint,%s" % k["fingerprint"], []],]
#                 vcards.append(vcard)
#             else:
#                 # Get the VCard
#                 session.ui.warning('Already exists: %s' % handle)
#  
#     return vcards


class OpenPGPCheckAddress(Command):
    ORDER = ('Config', 5)
    SYNOPSIS = ('', 'pgp/checkaddress', 'pgp/checkaddress', '<address>')
    HTTP_CALLABLE = ('GET', )
    HTTP_QUERY_VARS = {
        'q': 'address',
    }

    def command(self):
        addresses = self.data.get('q', [])
        g = GnuPG()
        res = {}
        for address in addresses:
            res[address] = g.address_to_keys(address)
        return res


class OpenPGPListKeys(Command):
    ORDER = ('Config', 5)
    SYNOPSIS = ('', 'pgp/listkeys', 'pgp/listkeys', '[<secret>]')
    HTTP_CALLABLE = ('GET', )
    HTTP_QUERY_VARS = {
       'secret': 'secret keys',
       'filter': 'filter',
    }

    def command(self):
        def filterrules(x):
            keyidmatch = x[0] == terms
            uidmatch = any([y[key].find(terms) != -1 for key in ["name", "email"] for y in x[1]["uids"]])
            return keyidmatch or uidmatch

        secret = self.data.get('secret', [])
        terms = self.data.get('filter', [])
        g = GnuPG()
        try:
            if len(secret) > 0:
                keys = g.list_secret_keys()[1]["stdout"][0]
            else:
                keys = g.list_keys()[1]["stdout"][0]
        except Exception, e:
            print e

        if terms != []:
            terms = " ".join(terms)
            return filter(filterrules, keys.items())
        else:
            return keys


class OpenPGPEncrypt(Command):
    ORDER = ('Config', 5)
    SYNOPSIS = ('', 'pgp/encrypt', 'pgp/encrypt', '<to> <data> [<sign> <from>]')
    HTTP_CALLABLE = ('GET', 'POST')
    HTTP_QUERY_VARS = {
        'to': 'encrypt messages to',
        'data': 'the data to encrypt',
        'sign': 'whether to sign (true/false, default=true)',
        'from': 'from which key (only if signing)'
    }

    def command(self):
        g = GnuPG()
        to = self.data.get('to', [])
        data = self.data.get('data', [])
        sign = self.data.get('sign', ["true"])[0] == "true"
        fromkey = "".join(self.data.get('from', [])) or None
        blobs = []
        for d in data:
            if sign:
                blob = g.sign_encrypt(d, fromkey, to)
                res = 0
            else:
                res, blob = g.encrypt(d, to)
            if res == 0:
                blobs.append(blob)

        return {"signed": sign, "from": fromkey, "to": to, "ciphertext": blobs}

class OpenPGPDecrypt(Command):
    ORDER = ('Config', 5)
    SYNOPSIS = ('', 'pgp/decrypt', 'pgp/decrypt', '<data>')
    HTTP_CALLABLE = ('GET', 'POST')
    HTTP_QUERY_VARS = {
        'data': 'the data to encrypt',
        'passphrase': 'the passphrase (optional)',
        'verify': 'whether to verify (true/false/auto, default=auto)'
    }

    def command(self):
        g = GnuPG()
        passphrase = "".join(self.data.get('passphrase', [])) or None
        data = self.data.get('data', [])
        blobs = []
        for d in data:
            res, blob = g.decrypt(d, passphrase)
            if res == 0:
                blobs.append(blob)

        return blobs


class OpenPGPSign(Command):
    ORDER = ('Config', 5)
    SYNOPSIS = ('', 'pgp/sign', 'pgp/sign', '<from> <data>')
    HTTP_CALLABLE = ('GET', 'POST')
    HTTP_QUERY_VARS = {
        'data': 'the data to sign',
        'from': 'from which key'
    }

    def command(self):
        g = GnuPG()
        data = self.data.get('data', [])
        fromkey = "".join(self.data.get('from', [])) or None
        blobs = []
        for d in data:
            res, blob = g.sign(d, fromkey, clearsign=True)
            if res == 0:
                blobs.append(blob)

        return {"from": fromkey, "ciphertext": blobs}


class OpenPGPVerify(Command):
    ORDER = ('Config', 5)
    SYNOPSIS = ('', 'pgp/verify', 'pgp/verify', '<data>')
    HTTP_CALLABLE = ('GET', 'POST')
    HTTP_QUERY_VARS = {
        'data': 'the data to verify',
    }

    def command(self):
        g = GnuPG()
        data = self.data.get('data', [])
        blobs = []
        for d in data:
            res, blob = g.verify(d)
            if res == 0:
                blobs.append(blob)

        return blobs


mailpile.plugins.register_commands(OpenPGPCheckAddress, OpenPGPListKeys, 
                                   OpenPGPEncrypt, OpenPGPDecrypt, 
                                   OpenPGPSign, OpenPGPVerify)
