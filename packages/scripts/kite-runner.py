#!/usr/bin/python
"""

kite-runner.py  - XMLRPC-based script launcher with PageKite integration.

"""
from __future__ import print_function
import getopt
import json
import os
import sys
import subprocess
import threading
import time
import traceback
try:
    import SimpleXMLRPCServer  # Python 2.7
except ImportError:
    import xmlrpc.server as SimpleXMLRPCServer  # Python 3.x


class ArgumentError(Exception):
    pass


class Killed(Exception):
    pass


class OutputEater(threading.Thread):
    def __init__(self, fd, callback):
        threading.Thread.__init__(self)
        self.daemon = True
        self.fd = fd
        self.cb = callback

    def run(self):
        while True:
            line = self.fd.readline()
            if not line:
                break
            self.cb(line.decode('utf-8').strip())
        self.cb(None)


class PagekiteThread(threading.Thread):
    def __init__(self, server):
        threading.Thread.__init__(self)
        self.kid = None
        self.server = server
        self.lock = threading.Lock()

    def _handle_logline(self, line):
        print(line)

    def run(self):
        try:
            self._run()
        finally:
            self.reap()

    def _run(self):
        skip_loops = 0
        crash_count = 0
        while not self.server.quitting:
            command = ' '.join([
                self.server.pagekite_binary,
                self.server.pagekite_args])
            command = command.replace('%PORT%', str(self.server.port))
            command = command.replace('%KITE%', self.server.pagekite_kite)
            command = command.replace('%SECRET%', self.server.pagekite_secret)
            with self.lock:
                if skip_loops:
                    skip_loops -= 1
                else:
                    print('Launching: %s' % command)
                    self.kid = subprocess.Popen(
                        [c for c in command.split() if c],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        env=self.server.subprocess_env(),
                        bufsize=0)
                    OutputEater(self.kid.stdout, self._handle_logline).start()
                    OutputEater(self.kid.stderr, self._handle_logline).start()
            rv = None
            time.sleep(0.5)
            while (self.kid is not None
                    and (rv is None)
                    and not self.server.quitting):
                with self.lock:
                    if self.kid is not None:
                        rv = self.kid.poll()
                        if rv is not None:
                            self.kid = None
                if rv not in (None, 0):
                    crash_count += 1
                    skip_loops = min(crash_count, 24) * 10
                    print('PageKite exited with status: %d' % rv)
                time.sleep(0.5)
        self.reap()

    def reap(self):
        with self.lock:
            if self.kid is not None:
                self.kid.kill()
                self.kid.wait()
                self.kid = None

    def quit(self):
        self.reap()
        self.join()


class BuildbotXMLRPCServer(SimpleXMLRPCServer.SimpleXMLRPCServer):
    def __init__(self, config, *args, **kwargs):
        SimpleXMLRPCServer.SimpleXMLRPCServer.__init__(self, *args, **kwargs)
        self.config = config


class BuildbotRequestHandler(SimpleXMLRPCServer.SimpleXMLRPCRequestHandler):
    def __init__(self, request, client_address, server):
        self.rpc_paths = server.config.rpc_paths
        SimpleXMLRPCServer.SimpleXMLRPCRequestHandler.__init__(
            self, request, client_address, server)


class BuildbotAPI(object):
    def __init__(self, server):
        self.server = server
        self.scripts = {}
        self.script_lock = threading.Lock()
        self.script_running = None
        self.script_last = None

    def _collect_stdout(self, sdata, logline):
        if logline is None:
            with self.script_lock:
                self.script_running = None
                self.script_last = sdata
            sdata[5] = sdata[0].wait()
            sdata[6] = time.time()
        else:
            sdata[3].append(logline)

    def _collect_stderr(self, sdata, logline):
        if logline is not None:
            sdata[4].append(logline)

    def status(self, name, error='No matching script logs found'):
        with self.script_lock:
            if self.script_running and self.script_running[1] == name:
                return self.script_running[1:]
            elif self.script_last and self.script_last[1] == name:
                return self.script_last[1:]
            else:
                raise ValueError(error)

    def run(self, name, delay):
        with self.script_lock:
            if name not in self.scripts:
                raise ValueError('No such script')
            elif self.script_running is None:
                kid = subprocess.Popen(
                    [self.server.shell_binary, '-c',
                     self.scripts[name].replace('\\', '\\\\\\\\')],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    env=self.server.subprocess_env(),
                    bufsize=0)
                sdata = [kid, name, time.time(), [], [], 0, 0]
                self.script_running = sdata
                OutputEater(
                    kid.stdout,
                    lambda ll: self._collect_stdout(sdata, ll)).start()
                OutputEater(
                    kid.stderr,
                    lambda ll: self._collect_stderr(sdata, ll)).start()
            elif self.script_running[1] != name:
                raise ValueError('Busy running other script(s)')

        time.sleep(max(0.1, min(5.0, float(delay))))
        return self.status(name)

    def test(self, arg):
        return 'You said: %s' % arg

    def quit(self):
        with self.script_lock:
            if self.script_running:
                self.script_running[0].kill()


class BuildbotServer(object):
    COMMON_OPT_FLAGS = 'p:k:c:'
    COMMON_OPT_ARGS = [
       'port=', 'runas=', 'config=',
       'xmlrpc_path=', 'sh_binary=', 'script=', 'bin_path=',
       'pagekite=', 'pk_binary=', 'pk_kite=', 'pk_secret=']

    DEFAULT_CONFIG_FILE = '~/kite-runner.cfg'
    DEFAULT_PORT = 33011

    def __init__(self):
        self.quitting = False
        self.port = self.DEFAULT_PORT
        self.api = BuildbotAPI(self)
        self.shell_binary = 'bash'
        self.rpc_paths = ('/KiteRunner',)
        self.bin_path = []
        self.pagekite_binary = 'pagekite'
        self.pagekite_kite = ''
        self.pagekite_secret = ''
        self.pagekite_args = None
        self.pagekite_thread = None
        self.config_file = os.path.expanduser(self.DEFAULT_CONFIG_FILE)
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

    def _set_uid_and_gid(self, identity):
        import pwd
        import grp
        parts = identity.split(':')
        pwnam = pwd.getpwnam(parts[0])
        if len(parts) > 1:
            uid, gid = pwnam.pw_uid, grp.getgrnam(parts[1]).gr_gid
        else:
            uid, gid = pwnam.pw_uid, pwnam.pw_gid
        os.setgid(gid)
        os.setuid(uid)

    def subprocess_env(self):
        env = os.environ.copy()
        env['HOME'] = os.getenv('HOME', os.path.expanduser('~'))
        env['PATH'] = os.getenv('PATH')
        for path in self.bin_path:
            env['PATH'] = '%s%s%s' % (path, os.pathsep, env['PATH'])
        return env

    def parse_with_common_args(self, args, opt_flags='', opt_args=[]):
        opts, args = getopt.getopt(
           args,
           '%s%s' % (opt_flags, self.COMMON_OPT_FLAGS),
           list(opt_args) + self.COMMON_OPT_ARGS)

        try:
            for opt, arg in opts:
                if opt in ('-p', '--port'):
                    self.port = int(arg.strip())

                if opt in ('--bin_path',):
                    self.bin_path.append(arg)

                if opt in ('--sh_binary',):
                    self.shell_binary = arg.strip()
                    if not os.path.exists(self.shell_binary):
                        raise ArgumentError('Not found: ' + self.shell_binary)

                if opt in ('--xmlrpc_path',):
                    self.rpc_paths = (arg,)

                if opt in ('--pk_binary',):
                    self.pagekite_binary = arg.strip()
                    if not os.path.exists(self.pagekite_binary):
                        raise ArgumentError(
                            'Not found: ' + self.pagekite_binary)

                if opt in ('--pk_kite',):
                    self.pagekite_kite = arg.strip()

                if opt in ('--pk_secret',):
                    self.pagekite_secret = arg.strip()

                if opt in ('--runas',):
                    self._set_uid_and_gid(arg)

                if opt in ('-k', '--pagekite'):
                    self.pagekite_args = arg.strip()

                if opt in ('--script',):
                    name, script = arg.split(':', 1)
                    self.api.scripts[name.strip()] = script.strip()

                if opt in ('-c', '--config'):
                    self.config_file = os.path.expanduser(arg)
                    if not os.path.exists(self.config_file):
                        raise ValueError('No such file: %s' % self.config_file)
                    self.load_config()

        except ValueError as e:
            raise ArgumentError(e)

        return opts, args

    def parse_args(self, args):
        self.parse_with_common_args(args)
        return self

    def launch_xmlrpc_server(self):
        rpc_server = BuildbotXMLRPCServer(
            self,
            ('localhost', self.port),
            requestHandler=BuildbotRequestHandler)
        rpc_server.register_introspection_functions()
        rpc_server.register_instance(self.api)
        rpc_server.serve_forever()

    def run(self):
        try:
            if self.pagekite_args:
                self.pagekite_thread = PagekiteThread(self)
                self.pagekite_thread.start()
            self.launch_xmlrpc_server()
        finally:
            self.quitting = True

    def cleanup(self):
        if self.pagekite_thread is not None:
            self.pagekite_thread.quit()
        self.api.quit()


def kite_runner_main(args):
    try:
        bb = BuildbotServer()
        bb.parse_args(args).run()
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
        bb.cleanup()


if __name__ == "__main__":
    kite_runner_main(sys.argv[1:])
