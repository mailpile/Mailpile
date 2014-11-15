import stem.process
import stem.control

import socks
import socket

SOCKS_PORT = 33419


class Tor:
    _instance = None
    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(Tor, cls).__new__(cls, *args, **kwargs)
        return cls._instance

    def __init__(self):
        self.tor_process = None
        self.original_socket = None
        self.original_getaddrinfo = None

    def start_tor(self):
        print "Starting Tor"
        self.tor_process = stem.process.launch_tor_with_config(
            config = {
                'SocksPort': str(SOCKS_PORT),
            },
            init_msg_handler = self._print_bootstrap_lines,
        )

    def _print_bootstrap_lines(self, line):
        pass

    def stop_tor(self):
        print "Stopping Tor"
        self.tor_process.kill()

    def create_hidden_service(self):
        pass

    def destroy_hidden_service(self):
        pass

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
    t.stop_tor()

