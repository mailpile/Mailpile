import copy
import socket
import subprocess
import threading
import time
import traceback
import re
import sys
import os

import stem.process
import stem.control

import mailpile.util
from mailpile.eventlog import Event
from mailpile.platforms import RandomListeningPort, GetDefaultTorPath
from mailpile.safe_popen import PresetSafePopenArgs, MakePopenSafe
from mailpile.util import okay_random

if 'pythonw' in sys.executable:
    debug_target = open( os.devnull, 'w' )
else:
    debug_target = sys.stdout

def debug( text ):
    debug_target.write( text + '\n' )
    debug_target.flush()

# Version check for STEM >= 1.4
assert(int(stem.__version__[0]) > 1 or
       (int(stem.__version__[0]) == 1 and int(stem.__version__[2]) >= 4))


class Tor(threading.Thread):
    _instance = None
    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(Tor, cls).__new__(cls, *args, **kwargs)
        return cls._instance

    def __init__(self, session=None, config=None,
                 socks_port=None, control_port=None, tor_binary=None,
                 callbacks=None):
        threading.Thread.__init__(self)
        self.session = session
        self.config = config or (session.config if session else None)
        self.callbacks = callbacks

        if self.config is None:
            self.socks_port = None
            self.control_port = None
            self.control_password = okay_random(32)
            self.tor_binary = tor_binary
        else:
            self.socks_port = self.config.sys.tor.socks_port
            self.control_port = self.config.sys.tor.ctrl_port
            self.control_password = self.config.sys.tor.ctrl_auth
            self.tor_binary = tor_binary or self.config.sys.tor.binary or None

        if socks_port is not None:
            self.socks_port = socks_port
        if control_port is not None:
            self.control_port = control_port

        self.event = Event(source=self, flags=Event.INCOMPLETE, data={})
        self.lock = threading.Lock()
        self.tor_process = None
        self.tor_controller = None
        self.hidden_services = {}
        self.keep_looping = True
        self.started = False

    def run(self):
        starts = 0
        while self.keep_looping and not mailpile.util.QUITTING:
            starts += 1
            try:
                self._run_once()
            except OSError:
                pass
            for i in range(0, 5 * min(60, starts)):
                if mailpile.util.QUITTING: break
                time.sleep(0.2)

    def _run_once(self):
        try:
            random_ports = RandomListeningPort(count=2)
            with self.lock:
                self.event.flags = Event.INCOMPLETE
                self.tor_process = 'starting up'
                self.tor_controller = None
                self.started = True

                if not self.socks_port:
                    self.socks_port = random_ports[0]
                if not self.control_port:
                    self.control_port = random_ports[1]
                if self.tor_binary is None:
                    self.tor_binary = GetDefaultTorPath()

                tor_process_config = {
                    'SocksPort': str(self.socks_port),
                    'ControlPort': str(self.control_port),
                    'HashedControlPassword': self._hashed_control_password()}

                self._log_line('Launching Tor (%s)' % self.tor_binary,
                               notify=True)

                PresetSafePopenArgs(long_running=True)
                self.tor_process = stem.process.launch_tor_with_config(
                    timeout=None,  # Required or signal.signal will raise
                    tor_cmd=self.tor_binary,
                    config= tor_process_config,
                    init_msg_handler=self._log_line)

                ctrl = stem.control.Controller.from_port(port=self.control_port)
                ctrl.authenticate(password=self.control_password)
                self.tor_controller = ctrl

            self.event.flags = Event.RUNNING
            self._log_line('Tor is live on socks=%d, control=%d'
                           % (self.socks_port, self.control_port),
                           notify=True)
        finally:
            MakePopenSafe()

        # Relaunch all the hidden services, if our Tor process died on us.
        self.relaunch_hidden_services()

        # Invoke any on-startup callbacks
        for cb in (self.callbacks or []):
            try:
                cb(self)
            except:
                self._log_line('Callback %s failed: %s'
                               % (cb, traceback.format_exc()),
                               notify=True)

        # Finally, just wait until our child process terminates.
        try:
            self.tor_process.wait()
        except:
            pass
        finally:
            self.event.flags = Event.COMPLETE
            self._log_line('Shut down', notify=True)
            self.tor_controller = None
            self.tor_process = None

    def _hashed_control_password(self):
        try:
            hasher = subprocess.Popen(
                [self.tor_binary, '--hush', '--hash-password',
                str(self.control_password)],
                stdout=subprocess.PIPE, bufsize=1)
            hasher.wait()
            expr = re.compile('([\d]{2}:[\w]{58})')
            match = filter(None, map(expr.match, hasher.stdout))[0]
            passhash = match.group(1)
            return passhash
        except:
            return None

    def _log_line(self, line, notify=False):
        if self.session:
            if notify:
                self.session.ui.notify(line)
            else:
                self.session.ui.debug(line)
        else:
            debug('%s' % line)

        log = self.event.data.get('log', [])
        log.append(line.strip())
        if len(log) > 100:
            log[:10] = []
        self.event.data['log'] = log
        if notify:
            self.event.message = line
            if self.config and self.config.event_log:
                self.config.event_log.log_event(self.event)

    def relaunch_hidden_services(self):
        hidden_services = copy.copy(self.hidden_services)
        for onion, (portmap, key_t, key_c) in hidden_services.iteritems():
            if key_t and key_c:
                self.launch_hidden_service(portmap, key_t, key_c)
            else:
                self._log_line('Failed to relaunch: %s' % onion, notify=True)

    def launch_hidden_service(self, portmap, key_type=None, key_content=None):
        with self.lock:
            aor = self.tor_controller.create_ephemeral_hidden_service(
                portmap,
                key_type=key_type if (key_content and key_type) else 'NEW',
                key_content=key_content or 'BEST',
                detached=True, await_publication=True)

        self.hidden_services[aor.service_id] = (
            portmap,
            aor.private_key_type or key_type,
            aor.private_key or key_content)
        self._log_line('Listening on Onion: %s.onion' % aor.service_id,
                       notify=True)
        return aor

    def stop_tor(self, wait=True):
        self.keep_looping = False
        if self.tor_process is not None:
            try:
                for onion in self.hidden_services:
                    try:
                        t.tor_controller.remove_ephemeral_hidden_service(onion)
                    except:
                        pass

                with self.lock:
                    self.tor_process.kill()
                if wait:
                    self.tor_process.wait()
            except:
                pass
            Tor._instance = None

    def isReady(self, wait=False):
         while True:
            if ((self.tor_process is not None) and
                    (self.tor_controller is not None)):
                return True
            if not wait:
                return False
            with self.lock:
                # If we have the lock, but self.tor_process is None, that
                # means startup has failed or we are dead - stop waiting!
                wait = (not self.started) or (self.tor_process is not None)
            if not self.started:
                time.sleep(0.1)

    def isAlive(self):
        # FIXME: This is inaccurate
        return (self.tor_process is not None)

    def quit(self, join=True):
        self.stop_tor(wait=join)


if __name__ == "__main__":
    TEST_KEY = "RSA1024:MIICXQIBAAKBgQDQ/+aYFpSvZZ5Ce2cpsuJz1epCcY9n+HZx/bC/D7mqEXCdDB9W13FMuwwK9FvjjXdfJzkdJ1GEcppEzd69C5xPZo2k+klKDhMONYhGHcm+CGu+JWNbqrcInNfZageu1Hg8g5Kz2h+/xCmuqKLSxGwJGvIoYfZupyn3DaxGnZv/2QIDAQABAoGAYs13L9MM+1Yo2PkJrhbZIzWvhzW0O8ykAgOSeOBwP0v7VuMSNbWn5ERQzyTyA8Mu+ZbLU1LxIJIlB/3jHK/Odoe2kkPjjaeKKVXGM+NMefps/YPs8abql06YoWN6KshY0BYkzkmlF/Xxl4t+jjvDG9Fsx6kJV6LKRwm6BFVzUTkCQQD2ujGQs1I1fsuCCHZXcnyoLO/hJaJLoj3clCiYcWhnfdpgkv0+CdIYE+DPZNsiIfruQQYZzZjKtO2xx0fvqKuPAkEA2Nq46nR1L0ISJizSfTYkz+KXuV8kgkMxwzkZC6l+DAqf4qxjFcDOwrIw9f75N8DcveHLD4R/fyMaesW6SK8KFwJAZ4Om1/bkPt17tIqoW/gEpOp1mhiYBvOC0NC4V3z9OK5suKfy59xm8QMmBt1hsuhexycw0BKaUDGoqDXb0IkLsQJBANQaUsWXdMrtX90Q+CxaGfVvVyGL6qSyXmjpXxLmDBBxD+Ng42VyeYk7SuJBKreanw3mXHvoB+BtkEfHQCY5dq8CQQCofoToQr5mTrlomus6/ei22Ein/BS9s0YUPCOpMkZfSp/GaWyEH7QjxatM/LoaMRlH/Y/wGMEK8P05F9DGBtSP"
    t = Tor()
    try:
        debug_target = open( sys.argv[1], 'w' )
    except IndexError:
        pass
    try:
        debug( "*** Starting Tor" )
        t.start()
        if t.isReady(wait=True):
            debug( "*** Creating hidden services..." )
            key_type, key_content = TEST_KEY.split(':', 1)
            aor = t.launch_hidden_service({80: 80}, key_type, key_content)
            aor = t.launch_hidden_service(443)

            #raw_input("*** Hit enter to disable service and shutdown ***")
            debug("waiting...")
            time.sleep(5)
    finally:
        debug("quiting!?!")
        t.quit()
        debug("exiting!?!")
