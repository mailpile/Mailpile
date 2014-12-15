import socks
import socket

import stem.process
import stem.control

# Version check for STEM >= 1.3
assert(int(stem.__version__[0]) > 1 or
       (int(stem.__version__[0]) == 1 and int(stem.__version__[2]) >= 3))


SOCKS_PORT = 33419
CONTROL_PORT = 33418


class Tor:
    _instance = None
    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(Tor, cls).__new__(cls, *args, **kwargs)
        return cls._instance

    def __init__(self, config=None):
        self.config = config
        self.tor_process = None
        self.original_socket = None
        self.original_getaddrinfo = None

    def start_tor(self):
        print "Starting Tor"
        self.tor_process = stem.process.launch_tor_with_config(
            config = {
                'SocksPort': str(SOCKS_PORT),
                'ControlPort': str(CONTROL_PORT),
            },
            init_msg_handler = self._print_bootstrap_lines,
        )

    def _print_bootstrap_lines(self, line):
        print '%s' % line
        pass

    def _create_path(self, name):
        if self.config:
            os.path.join(self.config.workdir, "tor", name)
        else:
            return name

    def stop_tor(self):
        print "Stopping Tor"
        self.tor_process.kill()

    def create_hidden_service(self, name, port, target):
        controller = stem.control.Controller.from_port(port=CONTROL_PORT)
        controller.authenticate()
        path = self._create_path(name)
        return controller.create_hidden_service(path, port, target)

    def destroy_hidden_service(self, name):
        controller = stem.control.Controller.from_port(port=CONTROL_PORT)
        controller.authenticate()
        path = self._create_path(name)
        controller.remove_hidden_service(name)

    def get_hidden_service_conf(self):
        controller = stem.control.Controller.from_port(port=CONTROL_PORT)
        controller.authenticate()
        return controller.get_hidden_service_conf()

    def start_proxying_through_tor(self):
        if self.original_socket:
            print "We're (probably) already proxying through Tor"
            return

        self.original_socket = socket.socket
        socks.setdefaultproxy(socks.PROXY_TYPE_SOCKS5, '127.0.0.1', SOCKS_PORT)
        socket.socket = socks.socksocket

    def stop_proxying_through_tor(self):
        if self.original_socket:
            socket.socket = self.original_socket
            self.original_socket = None

    def start_proxying_dns_through_tor(self):
        if self.original_getaddrinfo:
            print "We're already proxying DNS throug Tor"
            return

        self.original_getaddrinfo = socket.getaddrinfo

        def getaddrinfo(*args):
          return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', (args[0], args[1]))]

        socket.getaddrinfo = getaddrinfo

    def stop_proxying_dns_through_tor(self):
        if self.original_getaddrinfo:
            socket.getaddrinfo = self.original_getaddrinfo
            self.original_getaddrinfo = None


if __name__ == "__main__":
    import urllib
    url = "http://wtfismyip.com/text"

    print "BEWARE: This test script will probably leak your actual IP to wtfismyip.com."
    print "        But you shouldn't have run a test script that could fail if you didn't want this to happen."
    print "Your IP (not torified): %s" % (urllib.urlopen(url).read().strip())

    t = Tor()
    t.start_tor()
    t.start_proxying_through_tor()
    print "Your IP (torified): %s" % (urllib.urlopen(url).read().strip())
    t.stop_proxying_through_tor()

    print "Creating hidden service..."

    t.create_hidden_service("test", 80, "localhost:3000")

    print t.get_hidden_service_conf()

    input("Hit enter to disable service")

    t.destroy_hidden_service("meteor")

    t.stop_tor()

