#!/usr/bin/python
"""
FIXME...

"""
import getopt
import os
import time
import traceback
try:
    from xmlrpclib import ServerProxy  # Python 2.7
except ImportError:
    from xmlrpc.client import ServerProxy  # Python 3.x


class ArgumentError(Exception):
    pass


def config_assert(condition):
    if not condition:
        raise ArgumentError()


class BuildbotController(object):
    COMMON_OPT_FLAGS = 'c:'
    COMMON_OPT_ARGS = [
       'config=', 'buildmac_url=', 'buildwin_url=']

    DEFAULT_CONFIG_FILE = '~/.mailpile-build-controller.cfg'
    DEFAULT_PORT = 33011

    def __init__(self):
        self.config_file = os.path.expanduser(self.DEFAULT_CONFIG_FILE)
        self.buildmac_url = None
        self.buildwin_url = None
        self.running = None
        self.api = None
        if os.path.exists(self.config_file):
            self.load_config()

    def load_config(self, filename=None):
        with open(filename or self.config_file, 'r') as fd:
            lines = [l.split('#')[0].strip()
                     for l in fd.read().replace("\\\n", '').splitlines()]
        args = []
        for line in lines:
            if line:
                args.append('--%s' % line.replace(' = ', '='))
        return self.parse_args(args)

    def parse_with_common_args(self, args, opt_flags='', opt_args=[]):
        opts, args = getopt.getopt(
           args,
           '%s%s' % (opt_flags, self.COMMON_OPT_FLAGS),
           list(opt_args) + self.COMMON_OPT_ARGS)

        try:
            for opt, arg in opts:
                if opt in ('-c', '--config'):
                    self.config_file = os.path.expanduser(arg)
                    if not os.path.exists(self.config_file):
                        raise ValueError('No such file: %s' % self.config_file)
                    self.load_config()

                elif opt in ('--buildmac_url',):
                    self.buildmac_url = arg

                elif opt in ('--buildwin_url',):
                    self.buildwin_url = arg

        except ValueError as e:
            raise ArgumentError(e)

        return opts, args

    def cmd_hello(self, args):
        print 'Hello: %s' % ' '.join(args)
        args[:] = []

    def cmd_win(self, args):
        config_assert(self.buildwin_url is not None)
        self.api = ServerProxy(self.buildwin_url)
        self.running = None

    def cmd_mac(self, args):
        config_assert(self.buildmac_url is not None)
        self.api = ServerProxy(self.buildmac_url)
        self.running = None

    def cmd_run(self, args):
        config_assert(self.api is not None)
        self.running = args.pop(0)
        print('%s' % self.api.run(self.running, 1))

    def cmd_status(self, args):
        config_assert(self.api is not None)
        self.running = args.pop(0)
        print('%s' % self.api.status(self.running))

    def cmd_wait(self, args):
        config_assert(self.running is not None)
        while True:
            time.sleep(5)
            status = self.api.status(self.running)
            print('%s' % status)
            if status[-1]:
                break

    def parse_args(self, args):
        opts, args = self.parse_with_common_args(args)
        while args:
            command = args.pop(0)
            try:
                self.__getattribute__('cmd_%s' % command)(args)
            except AttributeError:
                raise ArgumentError('No such command: %s' % command)
        return self

    def run(self):
        pass

    def cleanup(self):
        pass

    @classmethod
    def Main(cls, args):
        bc = None
        try:
            bc = cls()
            bc.parse_args(args).run()
        except (getopt.GetoptError, ArgumentError):
            print(__doc__)
            traceback.print_exc()
            sys.exit(1)
        except (RuntimeError, KeyboardInterrupt):
            print('Quitting...')
        except Exception:
            traceback.print_exc()
            sys.exit(2)
        finally:
            if bc:
                bc.cleanup()


if __name__ == "__main__":
    import sys
    BuildbotController.Main(sys.argv[1:])
