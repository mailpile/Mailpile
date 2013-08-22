import mailpile.plugins
from mailpile.commands import Command
from mailpile.util import *

try:
  from GnuPGInterface import GnuPG
except ImportError:
  GnuPG = None


##[ Commands ]################################################################

class GPG(Command):
  """GPG commands"""
  ORDER = ('Config', 5)

  def recv_key(self):
    """Fetch a PGP public key from a keyserver."""

    session, config, arg = self.session, self.session.config, self.args[0]
    try:
      session.ui.mark('Invoking GPG to fetch key %s' % arg)
      keyserver = config.get('gpg_keyserver', 'pool.sks-keyservers.net')
      gpg = GnuPG().run(['--utf8-strings',
                         '--keyserver', keyserver,
                         '--recv-key', arg], create_fhs=['stderr'])
      session.ui.debug(gpg.handles['stderr'].read().decode('utf-8'))
      gpg.handles['stderr'].close()
      gpg.wait()
      session.ui.mark('Fetched key %s' % arg)
    except IOError:
      return self._error('Failed to fetch key %s' % arg)
    return True

  def list_keys(self):
    """Get a list of available PGP public keys."""

    session, config = self.session, self.session.config
    keys = []
    try:
      session.ui.mark('Listing available GPG keys')
      gpg = GnuPG().run(['--list-keys'], create_fhs=['stderr', 'stdout'])
      keylines = gpg.handles['stdout'].readlines()
      curkey = {}
      for line in keylines:
        if line[0:3] == "pub":
          if curkey != {}:
            keys.append(curkey)
            curkey = {}
          args = line.split("pub")[1].strip().split(" ")
          if len(args) == 3:
            expiry = args[2]
          else:
            expiry = None
          keytype, keyid = args[0].split("/")
          created = args[1]
          curkey["subkeys"] = []
          curkey["uids"] = []
          curkey["pub"] = {"keyid": keyid, "type": keytype, "created": created, "expires": expiry}
        elif line[0:3] == "sec":
          if curkey != {}:
            keys.append(curkey)
            curkey = {}
          args = line.split("pub")[1].strip().split(" ")
          if len(args) == 3:
            expiry = args[2]
          else:
            expiry = None
          keytype, keyid = args[0].split("/")
          created = args[1]
          curkey["subkeys"] = []
          curkey["uids"] = []
          curkey["sec"] = {"keyid": keyid, "type": keytype, "created": created, "expires": expiry}
        elif line[0:3] == "uid":
          curkey["uids"].append(line.split("uid")[1].strip())
        elif line[0:3] == "sub":
          args = line.split("sub")[1].strip().split(" ")
          if len(args) == 3:
            expiry = args[2]
          else:
            expiry = None
          keytype, keyid = args[0].split("/")
          created = args[1]
          curkey["subkeys"].append({"keyid": keyid, "type": keytype, "created": created, "expires": expiry})
      gpg.handles['stderr'].close()
      gpg.handles['stdout'].close()
      gpg.wait()
      session.ui.display_gpg_keys(keys)
    except IndexError, e:
      self._ignore_exception()
    except IOError:
      return False
    return True


  def fingerprints(self):
    """Fetch a key's fingerprints and other details."""
    session, config, arg = self.session, self.session.config, self.args[0]
    keys = []
    try:
      session.ui.mark('Listing available GPG keys')
      gpg = GnuPG().run(['--fingerprint', arg], create_fhs=['stderr', 'stdout'])
      keylines = gpg.handles['stdout'].readlines()
      raise Exception("IMPLEMENT ME!")
      session.ui.display_gpg_keys(keys)
    except IOError:
      return False
    return True

  def sign(self):
    """Sign a message."""
    session, config, arg = self.session, self.session.config, self.args[0]
    raise Exception("IMPLEMENT ME!")

  def verify(self):
    """Verify a signature."""
    session, config, arg = self.session, self.session.config, self.args[0]
    raise Exception("IMPLEMENT ME!")

  def encrypt(self):
    """Encrypt a message."""
    session, config, arg = self.session, self.session.config, self.args[0]
    raise Exception("IMPLEMENT ME!")

  def decrypt(self):
    """Decrypt a message."""
    session, config, arg = self.session, self.session.config, self.args[0]
    raise Exception("IMPLEMENT ME!")
    
  def sign_key(self):
    """Sign a public key."""
    session, config, arg = self.session, self.session.config, self.args[0]
    raise Exception("IMPLEMENT ME!")

  def send_key(self):
    """Upload a public key to a keyserver."""
    session, config, arg = self.session, self.session.config, self.args[0]
    raise Exception("IMPLEMENT ME!")

  def search_keys(self):
    """Search for a public key on keyservers, by string or key ID"""
    session, config, arg = self.session, self.session.config, self.args[0]
    raise Exception("IMPLEMENT ME!")

  SUBCOMMANDS = {
    'recv': (recv_key, '<key-ID>'),
    'list': (list_keys, ''),
    'fingerprints': (fingerprints, '<key-ID>'),
    'sign': (sign, '<msgid>'),
    'verify': (verify, '<msgid>'),
    'encrypt': (encrypt, '<msgid>'),
    'decrypt': (decrypt, '<msgid>'),
    'signkey': (sign_key, '<key-ID>'),
    'sendkey': (send_key, '<key-ID>'),
    'searchkeys': (search_keys, '<string>|<key-ID>'),
  }

  def command(self):
    session = self.session

    session.ui.mark("GPG Encryption interface. Use subcommands to interact:\n\n")
    for fun in self.SUBCOMMANDS.items():
      if fun[1][0].__doc__:
        session.ui.mark("  %12s %-18s:   %s\n" % (fun[0], fun[1][1], fun[1][0].__doc__))
      else:
        session.ui.mark("  %12s %-18s:   Undocumented\n" % (fun[0], fun[1][1]))

    session.ui.mark("")
    return True




if GnuPG is not None:
  mailpile.plugins.register_command('g:', 'gpg', GPG)
