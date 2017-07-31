# Connection brokers facilitate & manage incoming and outgoing connections.
#
# The idea is that code actually tells us what it wants to do, so we can
# choose an appropriate mechanism for connecting or receiving incoming
# connections.
#
# Libraries which use socket.create_connection can be monkey-patched
# to use a broker on a connection-by-connection bases like so:
#
#     with broker.context(need=[broker.OUTGOING_CLEARTEXT,
#                               broker.OUTGOING_SMTP]) as ctx:
#         conn = somelib.connect(something)
#         print 'Connected with encryption: %s' % ctx.encryption
#
# The context variable will then contain metadata about what sort of
# connection was made.
#
# See the Capability class below for a list of attributes that can be
# used to describe an outgoing (or incoming) connection.
#
# In particular, using the master broker will implement a prioritised
# connection strategy where the most secure options are tried first and
# things gracefully degrade. Protocols like IMAP, SMTP or POP3 will be
# transparently upgraded to use STARTTLS.
#
# TODO:
#    - Implement a TorBroker
#    - Implement a PageKiteBroker
#    - Implement HTTP/SMTP/IMAP/POP3 TLS upgrade-brokers
#    - Prevent unbrokered socket.socket connections
#
import datetime
import socket
import ssl
import subprocess
import sys
import threading
import time
import traceback

try:
    import cryptography
    import cryptography.hazmat.backends
    import cryptography.hazmat.primitives.hashes
    try:
        import cryptography.x509 as cryptography_x509
    except ImportError:
        cryptography_x509 = None
except ImportError:
    cryptography = None

# Import SOCKS proxy support...
try:
    import sockschain as socks
except ImportError:
    try:
        import socks
    except ImportError:
        socks = None

import mailpile.security as security
from mailpile.i18n import gettext
from mailpile.i18n import ngettext as _n
from mailpile.commands import Command
from mailpile.util import md5_hex, dict_merge, monkey_patch
from mailpile.security import tls_sock_cert_sha256


_ = lambda s: s

KNOWN_ONION_MAP = {
    'www.mailpile.is': 'clgs64523yi2bkhz.onion'
}


org_cconn = socket.create_connection


monkey_lock = threading.RLock()


def _explain_encryption(sock):
    try:
        algo, proto, bits = sock.cipher()
        return (
            _('%(tls_version)s (%(bits)s bit %(algorithm)s)')
        ) % {
            'bits': bits,
            'tls_version': proto,
            'algorithm': algo}
    except (ValueError, AttributeError):
        return _('no encryption')


class Capability(object):
    """
    These are constants defining different types of outgoing or incoming
    connections. Brokers use these to describe what sort of connections they
    are capable of handling, and calling code uses these to describe the
    intent of network connection.
    """
    OUTGOING_RAW = 'o:raw'      # Request this to avoid meddling brokers
    OUTGOING_ENCRYPTED = 'o:e'  # Request this if sending encrypted data
    OUTGOING_CLEARTEXT = 'o:c'  # Request this if sending clear-text data
    OUTGOING_TRACKABLE = 'o:t'  # Reject this to require anonymity
    OUTGOING_SMTP = 'o:smtp'    # These inform brokers what protocol is being
    OUTGOING_IMAP = 'o:imap'    # .. used, to allow protocol-specific features
    OUTGOING_POP3 = 'o:pop3'    # .. such as enabling STARTTLS or upgrading
    OUTGOING_HTTP = 'o:http'    # .. HTTP to HTTPS.
    OUTGOING_HTTPS = 'o:https'  # ..
    OUTGOING_SMTPS = 'o:smtps'  # ..
    OUTGOING_POP3S = 'o:pop3s'  # ..
    OUTGOING_IMAPS = 'o:imaps'  # ..

    INCOMING_RAW = 20
    INCOMING_LOCALNET = 21
    INCOMING_INTERNET = 22
    INCOMING_DARKNET = 23
    INCOMING_SMTP = 24
    INCOMING_IMAP = 25
    INCOMING_POP3 = 26
    INCOMING_HTTP = 27
    INCOMING_HTTPS = 28

    ALL_OUTGOING = set([OUTGOING_RAW, OUTGOING_ENCRYPTED, OUTGOING_CLEARTEXT,
                        OUTGOING_TRACKABLE,
                        OUTGOING_SMTP, OUTGOING_IMAP, OUTGOING_POP3,
                        OUTGOING_SMTPS, OUTGOING_IMAPS, OUTGOING_POP3S,
                        OUTGOING_HTTP, OUTGOING_HTTPS])

    ALL_OUTGOING_ENCRYPTED = set([OUTGOING_RAW, OUTGOING_TRACKABLE,
                                  OUTGOING_ENCRYPTED,
                                  OUTGOING_HTTPS, OUTGOING_SMTPS,
                                  OUTGOING_POP3S, OUTGOING_IMAPS])

    ALL_INCOMING = set([INCOMING_RAW, INCOMING_LOCALNET, INCOMING_INTERNET,
                        INCOMING_DARKNET, INCOMING_SMTP, INCOMING_IMAP,
                        INCOMING_POP3, INCOMING_HTTP, INCOMING_HTTPS])


class CapabilityFailure(IOError):
    """
    This exception is raised when capability requirements can't be satisfied.
    It extends the IOError, so unaware code just thinks the network is lame.

    >>> try:
    ...     raise CapabilityFailure('boo')
    ... except IOError:
    ...     print 'ok'
    ok
    """
    pass


class Url(str):
    def __init__(self, *args, **kwargs):
        str.__init__(self, *args, **kwargs)
        self.encryption = None
        self.anonymity = None
        self.on_internet = False
        self.on_localnet = False
        self.on_darknet = None


class BrokeredContext(object):
    """
    This is the context returned by the BaseConnectionBroker.context()
    method. It takes care of monkey-patching the socket.create_connection
    method and then cleaning the mess up afterwards, and collecting metadata
    from the brokers describing what sort of connection was established.

    WARNING: In spite of our best efforts (locking, etc.), mixing brokered
             and unbrokered code will not work well at all. The patching
             approach also limits us to initiating one outgoing connection
             at a time.
    """
    def __init__(self, broker, need=None, reject=None, oneshot=False):
        self._broker = broker
        self._need = need
        self._reject = reject
        self._oneshot = oneshot
        self._monkeys = []
        self._reset()

    def __str__(self):
        hostport = '%s:%s' % (self.address or ('unknown', 'none'))
        if self.error:
            return _('Failed to connect to %s: %s') % (hostport, self.error)

        if self.anonymity:
            network = self.anonymity
        elif self.on_darknet:
            network = self.on_darknet
        elif self.on_localnet:
            network = _('the local network')
        elif self.on_internet:
            network = _('the Internet')
        else:
            return _('Attempting to connect to %(host)s') % {'host': hostport}

        return _('Connected to %(host)s over %(network)s with %(encryption)s.'
                 ) % {
            'network': network,
            'host': hostport,
            'encryption': self.encryption or _('no encryption')
        }

    def _reset(self):
        self.error = None
        self.address = None
        self.encryption = None
        self.anonymity = None
        self.on_internet = False
        self.on_localnet = False
        self.on_darknet = None

    def _unmonkey(self):
        if self._monkeys:
            (socket.create_connection, ) = self._monkeys
            self._monkeys = []
            monkey_lock.release()

    def __enter__(self, *args, **kwargs):
        monkey_lock.acquire()
        self._monkeys = (socket.create_connection, )
        def create_brokered_conn(address, *a, **kw):
            self._reset()
            try:
                return self._broker.create_conn_with_caps(
                    address, self, self._need, self._reject, *a, **kw)
            finally:
                if self._oneshot:
                    self._unmonkey()
        socket.create_connection = create_brokered_conn
        return self

    def __exit__(self, *args, **kwargs):
        self._unmonkey()


class BaseConnectionBroker(Capability):
    """
    This is common code used by most of the connection brokers.
    """
    SUPPORTS = []

    def __init__(self, master=None):
        self.supports = list(self.SUPPORTS)[:]
        self.master = master
        self._config = None
        self._debug = master._debug if (master is not None) else None

    def configure(self):
        self.supports = list(self.SUPPORTS)[:]

    def set_config(self, config):
        self._config = config
        self.configure()

    def config(self):
        if self._config is not None:
            return self._config
        if self.master is not None:
            return self.master.config()
        return None

    def _raise_or_none(self, exc, why):
        if exc is not None:
            raise exc(why)
        return None

    def _check(self, need, reject, _raise=CapabilityFailure):
        for n in need or []:
            if n not in self.supports:
                if self._debug is not None:
                    self._debug('%s: lacking capabilty %s' % (self, n))
                return self._raise_or_none(_raise, 'Lacking %s' % n)
        for n in reject or []:
            if n in self.supports:
                if self._debug is not None:
                    self._debug('%s: unwanted capabilty %s' % (self, n))
                return self._raise_or_none(_raise, 'Unwanted %s' % n)
        if self._debug is not None:
            self._debug('%s: checks passed!' % (self, ))
        return self

    def _describe(self, context, conn):
        return conn

    def debug(self, val):
        self._debug = val
        return self

    def context(self, need=None, reject=None, oneshot=False):
        return BrokeredContext(self, need=need, reject=reject, oneshot=oneshot)

    def create_conn_with_caps(self, address, context, need, reject,
                              *args, **kwargs):
        if context.address is None:
            context.address = address
        conn = self._check(need, reject)._create_connection(context, address,
                                                            *args, **kwargs)
        return self._describe(context, conn)

    def create_connection(self, address, *args, **kwargs):
        n = kwargs.get('need', None)
        r = kwargs.get('reject', None)
        c = kwargs.get('context', None)
        for kw in ('need', 'reject', 'context'):
            if kw in kwargs:
                del kwargs[kw]
        return self.create_conn_with_caps(address, c, n, r, *args, **kwargs)

    # Should implement socket.create_connection or an equivalent.
    # Context, if not None, should be informed with metadata about the
    # connection.
    def _create_connection(self, context, address, *args, **kwargs):
        raise NotImplementedError('Subclasses override this')

    def get_urls(self, listening_fd,
                 need=None, reject=None, **kwargs):
        try:
            return self._check(need, reject)._get_urls(listening_fd, **kwargs)
        except CapabilityFailure:
            return []

    # Returns a list of Url objects for this listener
    def _get_urls(self, listening_fd,
                  proto=None, username=None, password=None):
        raise NotImplementedError('Subclasses override this')


class TcpConnectionBroker(BaseConnectionBroker):
    """
    The basic raw TCP/IP connection broker.

    The only clever thing this class does, is to avoid trying to connect
    to .onion addresses, preventing that from leaking over DNS.
    """
    SUPPORTS = (
        # Normal TCP/IP is not anonymous, and we do not have incoming
        # capability unless we have a public IP.
        (Capability.ALL_OUTGOING) |
        (Capability.ALL_INCOMING - set([Capability.INCOMING_INTERNET]))
    )
    LOCAL_NETWORKS = ['localhost', '127.0.0.1', '::1']
    FIXED_NO_PROXY_LIST = ['localhost', '127.0.0.1', '::1']
    DEBUG_FMT = '%s: Raw TCP conn to: %s'

    def configure(self):
        BaseConnectionBroker.configure(self)
        # FIXME: If our config indicates we have a public IP, add the
        #        INCOMING_INTERNET capability.

    def _describe(self, context, conn):
        (host, port) = conn.getpeername()[:2]
        if host.lower() in self.LOCAL_NETWORKS:
            context.on_localnet = True
        else:
            context.on_internet = True
        context.encryption = None
        return conn

    def _in_no_proxy_list(self, address):
        no_proxy = (self.FIXED_NO_PROXY_LIST +
                    [a.lower().strip()
                     for a in self.config().sys.proxy.no_proxy.split(',')])
        return (address[0].lower() in no_proxy)

    def _avoid(self, address):
        if (self.config().sys.proxy.protocol not in  ('none', 'unknown')
                and not self.config().sys.proxy.fallback
                and not self._in_no_proxy_list(address)):
            raise CapabilityFailure('Proxy fallback is disabled')

    def _broker_avoid(self, address):
        if address[0].endswith('.onion'):
            raise CapabilityFailure('Cannot connect to .onion addresses')

    def _conn(self, address, *args, **kwargs):
        clean_kwargs = dict((k, v) for k, v in kwargs.iteritems()
                            if not k.startswith('_'))
        return org_cconn(address, *args, **clean_kwargs)

    def _create_connection(self, context, address, *args, **kwargs):
        self._avoid(address)
        self._broker_avoid(address)
        if self._debug is not None:
            self._debug(self.DEBUG_FMT % (self, address))
        return self._conn(address, *args, **kwargs)


class SocksConnBroker(TcpConnectionBroker):
    """
    This broker offers the same services as the TcpConnBroker, but over a
    SOCKS connection.
    """
    SUPPORTS = []
    CONFIGURED = Capability.ALL_OUTGOING
    PROXY_TYPES = ('socks5', 'http', 'socks4')
    DEFAULT_PROTO = 'socks5'

    DEBUG_FMT = '%s: Raw SOCKS5 conn to: %s'
    IOERROR_FMT = _('SOCKS error, %s')
    IOERROR_MSG = {
        'timed out': _('timed out'),
        'Host unreachable': _('host unreachable'),
        'Connection refused': _('connection refused')
    }

    def __init__(self, *args, **kwargs):
        TcpConnectionBroker.__init__(self, *args, **kwargs)
        self.proxy_config = None
        self.typemap = {}

    def configure(self):
        BaseConnectionBroker.configure(self)
        if self.config().sys.proxy.protocol in self.PROXY_TYPES:
            self.proxy_config = self.config().sys.proxy
            self.supports = list(self.CONFIGURED)[:]
            self.typemap = {
                'socks5': socks.PROXY_TYPE_SOCKS5,
                'socks4': socks.PROXY_TYPE_SOCKS4,
                'http': socks.PROXY_TYPE_HTTP,
                'tor': socks.PROXY_TYPE_SOCKS5,       # For TorConnBroker
                'tor-risky': socks.PROXY_TYPE_SOCKS5  # For TorConnBroker
            }
        else:
            self.proxy_config = None
            self.supports = []

    def _auth_args(self):
        return {
            'username': self.proxy_config.username or None,
            'password': self.proxy_config.username or None
        }

    def _avoid(self, address):
        if self._in_no_proxy_list(address):
            raise CapabilityFailure('Proxy to %s:%s disabled by policy'
                                    ) % address

    def _fix_address_tuple(self, address):
        return (str(address[0]), int(address[1]))

    def _conn(self, address, timeout=None, source_address=None, **kwargs):
        sock = socks.socksocket()
        proxytype = self.typemap.get(self.proxy_config.protocol,
                                     self.typemap[self.DEFAULT_PROTO])
        sock.setproxy(proxytype=proxytype,
                      addr=self.proxy_config.host,
                      port=int(self.proxy_config.port),
                      rdns=True,
                      **self._auth_args())
        if timeout and timeout is not socket._GLOBAL_DEFAULT_TIMEOUT:
            sock.settimeout(float(timeout))
        if source_address:
            raise CapabilityFailure('Cannot bind source address')
        try:
            address = self._fix_address_tuple(address)
            sock.connect(address)
        except socks.ProxyError as e:
            if self._debug is not None:
                self._debug(traceback.format_exc())
            code, msg = e.message
            raise IOError(_(self.IOERROR_FMT
                            ) % (_(self.IOERROR_MSG.get(msg, msg)), ))
        return sock


class TorConnBroker(SocksConnBroker):
    """
    This broker offers the same services as the TcpConnBroker, but over Tor.

    This removes the "trackable" capability, so requests that reject it can
    find their way here safely...

    This broker only volunteers to carry encrypted traffic, because Tor
    exit nodes may be hostile.
    """
    SUPPORTS = []
    CONFIGURED = (Capability.ALL_OUTGOING_ENCRYPTED
                  - set([Capability.OUTGOING_TRACKABLE]))
    REJECTS = None
    PROXY_TYPES = ('tor', )
    DEFAULT_PROTO = 'tor'

    DEBUG_FMT = '%s: Raw Tor conn to: %s'
    IOERROR_FMT = _('Tor error, %s')
    IOERROR_MSG = dict_merge(SocksConnBroker.IOERROR_MSG, {
        'bad input': _('connection refused')  # FIXME: Is this right?
    })

    def _describe(self, context, conn):
        context.on_darknet = 'Tor'
        context.anonymity = 'Tor'
        return conn

    def _auth_args(self):
        # FIXME: Tor uses the auth information as a signal to change
        #        circuits. We may have use for this at some point.
        return {}

    def _fix_address_tuple(self, address):
        host = str(address[0])
        return (KNOWN_ONION_MAP.get(host.lower(), host), int(address[1]))

    def _broker_avoid(self, address):
        # Disable the avoiding of .onion addresses added above
        pass


class TorRiskyBroker(TorConnBroker):
    """
    This differs from the TorConnBroker in that it will allow "cleartext"
    traffic to anywhere - this is dangerous, because exit nodes could mess
    with our traffic.
    """
    CONFIGURED = (Capability.ALL_OUTGOING
                  - set([Capability.OUTGOING_TRACKABLE]))
    DEBUG_FMT = '%s: Risky Tor conn to: %s'
    PROXY_TYPES = ('tor-risky', )
    DEFAULT_PROTO = 'tor-risky'


class TorOnionBroker(TorConnBroker):
    """
    This broker offers the same services as the TcpConnBroker, but over Tor.

    This removes the "trackable" capability, so requests that reject it can
    find their way here safely...

    This differs from the TorConnBroker in that it will allow "cleartext"
    traffic, since we trust the traffic never leaves the Tor network and
    we don't have hostile exits to worry about.
    """
    SUPPORTS = []
    CONFIGURED = (Capability.ALL_OUTGOING
                  - set([Capability.OUTGOING_TRACKABLE]))
    REJECTS = None
    DEBUG_FMT = '%s: Tor onion conn to: %s'
    PROXY_TYPES = ('tor', 'tor-risky')

    def _broker_avoid(self, address):
        host = KNOWN_ONION_MAP.get(address[0], address[0])
        if not host.endswith('.onion'):
            raise CapabilityFailure('Can only connect to .onion addresses')


class BaseConnectionBrokerProxy(TcpConnectionBroker):
    """
    Brokers based on this establish a RAW connection and then manipulate it
    in some way, generally to implement proxying or TLS wrapping.
    """
    SUPPORTS = []
    WANTS = [Capability.OUTGOING_RAW]
    REJECTS = None

    def _proxy_address(self, address):
        return address

    def _proxy(self, conn):
        raise NotImplementedError('Subclasses override this')

    def _wrap_ssl(self, conn):
        if self._debug is not None:
            self._debug('%s: Wrapping socket with SSL' % (self, ))
        return ssl.wrap_socket(conn)

    def _create_connection(self, context, address, *args, **kwargs):
        address = self._proxy_address(address)
        if self.master:
            conn = self.master.create_conn_with_caps(
                address, context, self.WANTS, self.REJECTS, *args, **kwargs)
        else:
            conn = TcpConnectionBroker._create_connection(self, context,
                                                          address,
                                                          *args, **kwargs)
        return self._proxy(conn)


class AutoTlsConnBroker(BaseConnectionBrokerProxy):
    """
    This broker tries to auto-upgrade connections to use TLS, or at
    least do the SSL handshake here so we can record info about it.
    """
    SUPPORTS = [Capability.OUTGOING_HTTP, Capability.OUTGOING_HTTPS,
                Capability.OUTGOING_IMAPS, Capability.OUTGOING_SMTPS,
                Capability.OUTGOING_POP3S]
    WANTS = [Capability.OUTGOING_RAW, Capability.OUTGOING_ENCRYPTED]

    def _describe(self, context, conn):
        context.encryption = _explain_encryption(conn)
        return conn

    def _proxy_address(self, address):
        if address[0].endswith('.onion'):
            raise CapabilityFailure('I do not like .onion addresses')
        if int(address[1]) != 443:
            # FIXME: Import HTTPS Everywhere database to make this work?
            raise CapabilityFailure('Not breaking clear-text HTTP yet')
        return address

    def _proxy(self, conn):
        return self._wrap_ssl(conn)


class AutoSmtpStartTLSConnBroker(BaseConnectionBrokerProxy):
    pass


class AutoImapStartTLSConnBroker(BaseConnectionBrokerProxy):
    pass


class AutoPop3StartTLSConnBroker(BaseConnectionBrokerProxy):
    pass


class MasterBroker(BaseConnectionBroker):
    """
    This is the master broker. It implements a prioritised list of
    connection brokers, each of which is tried in turn until a match
    is found. As such, more secure brokers should register themselves
    with a higher priority - if they fail, we fall back to less
    secure connection strategies.
    """
    def __init__(self, *args, **kwargs):
        BaseConnectionBroker.__init__(self, *args, **kwargs)
        self.brokers = []
        self.history = []
        self._debug = self._debugger
        self.debug_callback = None

    def configure(self):
        for prio, cb in self.brokers:
            cb.configure()

    def _debugger(self, *args, **kwargs):
        if self.debug_callback is not None:
            self.debug_callback(*args, **kwargs)

    def register_broker(self, priority, cb):
        """
        Brokers should register themselves with priorities as follows:

           - 1000-1999: Content-agnostic raw connections
           - 3000-3999: Secure network layers: VPNs, Tor, I2P, ...
           - 5000-5999: Proxies required to reach the wider Internet
           - 7000-7999: Protocol enhancments (non-security related)
           - 9000-9999: Security-related protocol enhancements

        """
        self.brokers.append((priority, cb(master=self)))
        self.brokers.sort()
        self.brokers.reverse()

    def get_fd_context(self, fileno):
        for t, fd, context in reversed(self.history):
            if fd == fileno:
                return context
        return BrokeredContext(self)

    def create_conn_with_caps(self, address, context, need, reject,
                              *args, **kwargs):
        history_event = kwargs.get('_history_event')
        if history_event is None:
            history_event = [int(time.time()), None, context]
            self.history = self.history[-50:]
            self.history.append(history_event)
            kwargs['_history_event'] = history_event
        else:
            history_event[-1] = context

        if context.address is None:
            context.address = address

        et = v = t = None
        for prio, cb in self.brokers:
            try:
                conn = cb.debug(self._debug).create_conn_with_caps(
                    address, context, need, reject, *args, **kwargs)
                if conn:
                    history_event[1] = conn.fileno()
                    return conn
            except (CapabilityFailure, NotImplementedError):
                # These are internal; we assume they're already logged
                # for debugging but don't bother the user with them.
                pass
            except:
                et, v, t = sys.exc_info()
        if et is not None:
            context.error = '%s' % v
            raise et, v, t

        context.error = _('No connection method found')
        raise CapabilityFailure(context.error)

    def get_urls(self, listening_fd, need=None, reject=None):
        urls = []
        for prio, cb in self.brokers:
            urls.extend(cb.debug(self._debug).get_urls(listening_fd))
        return urls


def DisableUnbrokeredConnections():
    """Enforce the use of brokers EVERYWHERE!"""
    def CreateConnWarning(*args, **kwargs):
        print '*** socket.create_connection used without a broker ***'
        traceback.print_stack()
        raise IOError('FIXME: Please use within a broker context')
    socket.create_connection = CreateConnWarning


class NetworkHistory(Command):
    """Show recent network history"""
    SYNOPSIS = (None, 'logs/network', 'logs/network', None)
    ORDER = ('Internals', 6)
    CONFIG_REQUIRED = False
    IS_USER_ACTIVITY = False

    class CommandResult(Command.CommandResult):
        def as_text(self):
            if self.result:
                def fmt(result):
                    dt = datetime.datetime.fromtimestamp(result[0])
                    return '%2.2d:%2.2d %s' % (dt.hour, dt.minute, result[-1])
                return '\n'.join(fmt(r) for r in self.result)
            return _('No network events recorded')

    def command(self):
        return self._success(_('Listed recent network events'),
                             result=Master.history)


class GetTlsCertificate(Command):
    """Fetch and parse a server's TLS certificate"""
    SYNOPSIS = (None, 'crypto/tls/getcert', 'crypto/tls/getcert', '[--tofu-save|--tofu-clear]')
    ORDER = ('Internals', 6)
    CONFIG_REQUIRED = False
    IS_USER_ACTIVITY = False
    HTTP_CALLABLE = ('GET', 'POST')
    HTTP_QUERY_VARS = {
        'tofu-clear': 'Remove from TOFU certificate store',
        'tofu-save': 'Save to our TOFU certificate store',
        'host': 'Name of remote server'
    }

    class CommandResult(Command.CommandResult):
        def as_text(self):
            if self.result:
                def fmt(h, r):
                    return '%s:\t%s' % (h, r[-1] or r[1])
                return '\n'.join(fmt(h, r) for h, r in self.result.iteritems())
            return _('No certificates found')

    def command(self):
        if self.data.get('_method', 'POST') != 'POST':
            # Allow HTTP GET as a no-op, so the user can see a friendly form.
            return self._success(_('Examine TLS certificates'))

        config = self.session.config
        tofu_save = self.data.get('tofu-save', '--tofu-save' in self.args)
        tofu_clear = self.data.get('tofu-clear', '--tofu-clear' in self.args)
        hosts = (list(s for s in self.args if not s.startswith('--')) +
                 self.data.get('host', []))

        def ts(t):
            return int(time.mktime(t.timetuple()))

        def oidName(oid):
            return {
                '2.5.4.3': 'commonName',
                '2.5.4.4': 'surname',
                '2.5.4.5': 'serialNumber',
                '2.5.4.6': 'countryName',
                '2.5.4.7': 'localityName',
                '2.5.4.8': 'stateOrProvinceName',
                '2.5.4.9': 'streetAddress',
                '2.5.4.10': 'organizationName',
                '2.5.4.11': 'organizationalUnitName'
                }.get(oid.dotted_string,
                      getattr(oid, '_name', oid.dotted_string))

        def oidmap(entries):
            return dict((oidName(e.oid), e.value) for e in entries)

        def subjmap(stext):
            def subjpair(kv):
                k, v = kv.split('=', 1)
                return ({'CN': 'commonName',
                         'C': 'countryName',
                         'ST': 'stateOrProvinceName',
                         'L': 'localityName',
                         'O': 'organizationName',
                         'OU': 'organizationalUnitName'}.get(k, k), v)
            parts = []
            for part in stext.strip().split('/'):
                if '=' in part:
                    parts.append(part)
                elif parts:
                    parts[-1] += '/' + part
            return dict(subjpair(kv) for kv in parts)

        def fingerprint(cert_sha_256):
            fp = ['%2.2x' % ord(b) for b in cert_sha_256]
            fp2 = [fp[i*2] + fp[i*2 + 1] for i in range(0, len(fp)/2)]
            return fp2

        def pts(t):
            dt, tz = t.rsplit(' ', 1)  # Strip off the timezone
            return datetime.datetime.strptime(dt, '%b %d %H:%M:%S %Y')

        def parse_pem_cert(cert_pem, s256):
            cert_sha_256 = s256.decode('base64')
            now = datetime.datetime.today()
            if cryptography_x509 is None:
                # Shell out to openssl, boo.
                (stdout, stderr) = subprocess.Popen(
                    ['openssl', 'x509',
                        '-subject', '-issuer', '-dates', '-noout'],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    stdin=subprocess.PIPE).communicate(input=str(cert_pem))
                if not stdout:
                    raise ValueError(stderr)
                details = dict(l.split('=', 1)
                               for l in stdout.strip().splitlines()
                               if l and '=' in l)
                details['notAfter'] = pts(details['notAfter'])
                details['notBefore'] = pts(details['notBefore'])
                return {
                    'fingerprint': fingerprint(cert_sha_256),
                    'date_matches': False,
                    'date_matches': ((details['notBefore'] < now) and
                                     (details['notAfter'] > now)),
                    'not_valid_before': ts(details['notBefore']),
                    'not_valid_after': ts(details['notAfter']),
                    'subject': subjmap(details['subject']),
                    'issuer': subjmap(details['issuer'])}
            else:
                parsed = cryptography_x509.load_pem_x509_certificate(
                    str(cert_pem),
                    cryptography.hazmat.backends.default_backend())
                return {
                    'fingerprint': fingerprint(cert_sha_256),
                    'date_matches': ((parsed.not_valid_before < now) and
                                     (parsed.not_valid_after > now)),
                    'not_valid_before': ts(parsed.not_valid_before),
                    'not_valid_after': ts(parsed.not_valid_after),
                    'subject': oidmap(parsed.subject),
                    'issuer': oidmap(parsed.issuer)}

        def attempt_starttls(addr, sock):
            # Attempt a minimal SMTP interaction, for STARTTLS support

            # We attempt a non-blocking peek unless we're sure this is
            # a port normally used for clear-text SMTP.
            peeking = int(addr[1]) not in (25, 587, 143)

            # If this isn't a known TLS port, then we sleep a bit to give a
            # greeting time to arrive.
            if peeking and int(addr[1]) not in (443, 465, 993, 995):
                time.sleep(0.4)

            try:
                # Look for an SMTP (or IMAP) greeting
                if peeking:
                    sock.setblocking(0)
                    # Note: This will throw a TypeError if we are connected
                    #       over Tor (or other SOCKS).
                    first = sock.recv(1024, socket.MSG_PEEK) or ''
                else:
                    sock.settimeout(10)
                    first = sock.recv(1024) or ''

                if first[:4] == '220 ':
                    # This is an SMTP greeting
                    if peeking:
                        sock.setblocking(1)
                        sock.recv(1024)
                    sock.sendall('EHLO example.com\r\n')
                    if (sock.recv(1024) or '')[:1] == '2':
                        sock.sendall('STARTTLS\r\n')
                        sock.recv(1024)

                elif first[:4] == '* OK':
                    # This is an IMAP4 greeting
                    if peeking:
                        sock.setblocking(1)
                        sock.recv(1024)
                    sock.sendall('* STARTTLS\r\n')
                    sock.recv(1024)

            except (TypeError, IOError, OSError):
                pass
            finally:
                sock.setblocking(1)

        certs = {}
        ok = changes = 0
        for host in hosts:
            try:
                addr = host.replace(' ', '').split(':') + ['443']
                addr = (addr[0], int(addr[1]))

                try:
                    with Master.context(need=[Master.OUTGOING_ENCRYPTED,
                                              Master.OUTGOING_RAW]) as ctx:
                        sock = socket.create_connection(addr, timeout=30)
                    attempt_starttls(addr, sock)
                    ssls = ssl.wrap_socket(sock, use_web_ca=True, tofu=False)
                    hostname_matches = True
                    cert_validated = True

                except (ssl.SSLError, ssl.CertificateError) as e:
                    if isinstance(e, ssl.CertificateError):
                        cert_validated = True
                        hostname_matches = False
                    else:
                        cert_validated = False
                        hostname_matches = 'unknown'

                    with Master.context(need=[Master.OUTGOING_ENCRYPTED,
                                              Master.OUTGOING_RAW]) as ctx:
                        sock = socket.create_connection(addr, timeout=30)
                    attempt_starttls(addr, sock)
                    ssls = ssl.wrap_socket(sock, use_web_ca=False, tofu=False)

                cert = ssls.getpeercert(True)
                s256 = tls_sock_cert_sha256(cert=cert)
                ssls.close()

                cfg_key = md5_hex('%s:%d' % addr)
                if tofu_clear:
                    if cfg_key in config.tls.keys():
                        del config.tls[cfg_key]
                        changes += 1
                if tofu_save:
                    if cfg_key not in config.tls.keys():
                        config.tls[cfg_key] = {'server': '%s:%d' % addr}
                    cert_tofu = config.tls[cfg_key]
                    cert_tofu.use_web_ca = False
                    cert_tofu.accept_certs.append(s256)
                    changes += 1
                else:
                    cert_tofu = config.tls.get(cfg_key, {})

                tofu_seen = s256 in cert_tofu.get('accept_certs', [])
                using_tofu = not cert_tofu.get('use_web_ca', True)
                cert = {
                    'current_time': int(time.time()),
                    'cert_validated': cert_validated,
                    'hostname_matches': hostname_matches,
                    'tofu_seen': tofu_seen,
                    'using_tofu': using_tofu,
                    'tofu_invalid': (using_tofu and not tofu_seen),
                    'pem': ssl.DER_cert_to_PEM_cert(cert)}

                cert.update(parse_pem_cert(cert['pem'], s256))

                certs[host] = (True, s256, cert, None)
                ok += 1
            except Exception as e:
                certs[host] = (
                    False, _('Failed to fetch certificate'), unicode(e),
                    traceback.format_exc())

        if changes:
            self._background_save(config=True)

        if ok:
            return self._success(_('Downloaded TLS certificates'),
                                 result=certs)
        else:
            return self._error(_('Failed to download TLS certificates'),
                               result=certs)


def SslWrapOnlyOnce(org_sslwrap, sock, *args, **kwargs):
    """
    Since we like to wrap things our own way, this make ssl.wrap_socket
    into a no-op in the cases where we've alredy wrapped a socket.
    """
    if not isinstance(sock, ssl.SSLSocket):
        ctx = Master.get_fd_context(sock.fileno())
        try:
            if 'server_hostname' not in kwargs:
                kwargs['server_hostname'] = ctx.address[0]
            sock = org_sslwrap(sock, *args, **kwargs)
            ctx.encryption = _explain_encryption(sock)
        except (socket.error, IOError, ssl.SSLError, ssl.CertificateError), e:
            ctx.error = '%s' % e
            raise
    return sock


def SslContextWrapOnlyOnce(org_ctxwrap, self, sock, *args, **kwargs):
    return SslWrapOnlyOnce(
        lambda s, *a, **kwa: org_ctxwrap(self, s, *a, **kwa),
        sock, *args, **kwargs)


_ = gettext

if __name__ != "__main__":
    Master = MasterBroker()
    register = Master.register_broker
    register(1000, TcpConnectionBroker)
    register(9500, AutoTlsConnBroker)
    register(9500, AutoSmtpStartTLSConnBroker)
    register(9500, AutoImapStartTLSConnBroker)
    register(9500, AutoPop3StartTLSConnBroker)

    if socks is not None:
        register(1500, SocksConnBroker)
        register(3500, TorConnBroker)
        register(3500, TorRiskyBroker)
        register(3500, TorOnionBroker)

    # Note: At this point we have already imported security, which
    #       also monkey-patches these same functions. This is a good
    #       thing and is deliberate. :-)
    ssl.wrap_socket = monkey_patch(ssl.wrap_socket, SslWrapOnlyOnce)
    if hasattr(ssl, 'SSLContext'):
        ssl.SSLContext.wrap_socket = monkey_patch(
           ssl.SSLContext.wrap_socket, SslContextWrapOnlyOnce)

    from mailpile.plugins import PluginManager
    _plugins = PluginManager(builtin=__file__)
    _plugins.register_commands(NetworkHistory, GetTlsCertificate)

else:
    import doctest
    import sys
    results = doctest.testmod(optionflags=doctest.ELLIPSIS,
                              extraglobs={})
    print '%s' % (results, )
    if results.failed:
        sys.exit(1)
