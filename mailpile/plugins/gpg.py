import mailpile.plugins
from mailpile.commands import Command
from mailpile.util import *


##[ Commands ]################################################################

class GPG(Command):
  """GPG commands"""
  ORDER = ('Config', 5)
  def command(self):
    raise Exception('FIXME: Should print instructions')

  def recv_key(self):
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

  SUBCOMMANDS = {
    'recv': (recv_key, '<key-ID>'),
    'list': (list_keys, '')
  }


mailpile.plugins.register_command('g:', 'gpg', GPG)
