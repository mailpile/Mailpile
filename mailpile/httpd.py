#
# Mailpile's built-in HTTPD
#
###############################################################################
import mimetypes
import os
import socket
import SocketServer
from SimpleXMLRPCServer import SimpleXMLRPCServer, SimpleXMLRPCRequestHandler
from urllib import quote, unquote
from urlparse import parse_qs, urlparse

import mailpile.util
from mailpile.commands import Action
from mailpile.urlmap import UrlMap
from mailpile.util import *
from mailpile.ui import *

global APPEND_FD_CACHE, APPEND_FD_CACHE_ORDER, APPEND_FD_CACHE_SIZE
global WORD_REGEXP, STOPLIST, BORING_HEADERS, DEFAULT_PORT

DEFAULT_PORT = 33411


class HttpRequestHandler(SimpleXMLRPCRequestHandler):

  _ERROR_CONTEXT = {'lastq': '', 'csrf': '', 'path': ''},

  def http_host(self):
    """Return the current server host, e.g. 'localhost'"""
    #rsplit removes port
    return self.headers.get('host', 'localhost').rsplit(':', 1)[0]

  def server_url(self):
    """Return the current server URL, e.g. 'http://localhost:33411/'"""
    return '%s://%s' % (self.headers.get('x-forwarded-proto', 'http'),
                        self.headers.get('host', 'localhost'))

  def send_http_response(self, code, msg):
    """Send the HTTP response header"""
    self.wfile.write('HTTP/1.1 %s %s\r\n' % (code, msg))

  def send_http_redirect(self, destination):
    self.send_http_response(302, 'Moved Temporarily')
    self.wfile.write('Location: %s\r\n\r\n' % destination)

  def send_standard_headers(self, header_list=[],
                            cachectrl='private', mimetype='text/html'):
    """
    Send common HTTP headers plus a list of custom headers:
    - Cache-Control
    - Content-Type

    This function does not send the HTTP/1.1 header, so
    ensure self.send_http_response() was called before

    Keyword arguments:
    header_list -- A list of custom headers to send, containing key-value tuples
    cachectrl   -- The value of the 'Cache-Control' header field
    mimetype    -- The MIME type to send as 'Content-Type' value
    """
    if mimetype.startswith('text/') and ';' not in mimetype:
      mimetype += ('; charset=utf-8')
    self.send_header('Cache-Control', cachectrl)
    self.send_header('Content-Type', mimetype)
    for header in header_list:
      self.send_header(header[0], header[1])
    self.end_headers()

  def send_full_response(self, message, code=200, msg='OK', mimetype='text/html',
                         header_list=[], suppress_body=False):
    """
    Sends the HTTP header and a response list

    message       -- The body of the response to send
    header_list   -- A list of custom headers to send,
                     containing key-value tuples
    code          -- The HTTP response code to send
    mimetype      -- The MIME type to send as 'Content-Type' value
    suppress_body -- Set this to True to ignore the message parameter
                     and not send any response body
    """
    message = unicode(message).encode('utf-8')
    self.log_request(code, message and len(message) or '-')
    #Send HTTP/1.1 header
    self.send_http_response(code, msg)
    #Send all headers
    if code == 401:
      self.send_header('WWW-Authenticate',
                       'Basic realm=MP%d' % (time.time()/3600))
    #If suppress_body == True, we don't know the content length
    contentLengthHeaders = []
    if not suppress_body:
        contentLengthHeaders = [ ('Content-Length', len(message or '')) ]
    self.send_standard_headers(header_list=header_list + contentLengthHeaders,
                               mimetype=mimetype,
                               cachectrl="no-cache")
    #Response body
    if not suppress_body:
      self.wfile.write(message or '')

  def send_file(self, config, filename):
    # FIXME: Do we need more security checks?
    if '..' in filename:
      code, msg = 403, "Access denied"
    else:
      try:
        tpl = config.get('path', {}).get(self.http_host(), 'html_theme')
        fpath, fd = config.open_file(tpl, filename)
        mimetype = mimetypes.guess_type(fpath)[0] or "application/octet-stream"
        message = fd.read()
        fd.close()
        code, msg = 200, "OK"
      except IOError, e:
        if e.errno == 2:
          code, msg, mimetype = 404, "File not found", 'text/plain'
        elif e.errno == 13:
          code, msg, mimetype = 403, "Access denied", 'text/plain'
        else:
          code, msg, mimetype = 500, "Internal server error", 'text/plain'
        message = ""

    self.log_request(code, message and len(message) or '-')
    self.send_http_response(code, msg)
    self.send_standard_headers(header_list=[
                                 ('Content-Length', len(message or ''))
                               ],
                               mimetype=mimetype,
                               cachectrl="must-revalidate=False, max-age=3600")
    self.wfile.write(message or '')

  def csrf(self):
    """
    Generate a hashed token from the current timestamp
    and the server secret to avoid CSRF attacks
    """
    ts = '%x' % int(time.time()/60)
    return '%s-%s' % (ts, b64w(sha1b64('-'.join([self.server.secret, ts]))))

  def do_POST(self, method='POST'):
    (scheme, netloc, path, params, query, frag) = urlparse(self.path)
    if path.startswith('/::XMLRPC::/'):
      raise ValueError('XMLRPC has been disabled for now.')
      #return SimpleXMLRPCRequestHandler.do_POST(self)

    config = self.server.session.config
    post_data = { }
    try:
      ue = 'application/x-www-form-urlencoded'
      clength = int(self.headers.get('content-length', 0))
      ctype, pdict = cgi.parse_header(self.headers.get('content-type', ue))
      if ctype == 'multipart/form-data':
        post_data = cgi.FieldStorage(
          fp=self.rfile,
          headers=self.headers,
          environ={'REQUEST_METHOD': method,
                   'CONTENT_TYPE': self.headers['Content-Type']}
        )
      elif ctype == ue:
        if clength > 5*1024*1024:
          raise ValueError('OMG, input too big')
        post_data = cgi.parse_qs(self.rfile.read(clength), 1)
      else:
        raise ValueError('Unknown content-type')

    except (IOError, ValueError), e:
      r = self.server.session.ui.render_page(config, self._ERROR_CONTEXT,
                                             body='POST geborked: %s' % e,
                                             title='Internal Error')
      self.send_full_response(r, code=500)
      return None
    return self.do_GET(post_data=post_data, method=method)

  def do_GET(self, post_data={}, suppress_body=False, method='GET'):
    (scheme, netloc, path, params, query, frag) = urlparse(self.path)
    query_data = parse_qs(query)
    path = unquote(path)

    # HTTP is stateless, so we create a new session for each request.
    config = self.server.session.config

    if 'http' in config.get('debug', ''):
      sys.stderr.write(('%s: %s qs=%s post=%s\n'
                        ) % (method, path, query_data, post_data))

    # Static things!
    if path == '/favicon.ico':
      path = '/static/favicon.ico'
    if path.startswith('/_/'):
      path = path[2:]
    if path.startswith('/static/'):
      return self.send_file(config, path[len('/static/'):])

    session = Session(config)
    session.ui = HttpUserInteraction(self, config)

    idx = session.config.index
    session.ui.html_variables = {
      'http_host': self.headers.get('host', 'localhost'),
      'http_hostname': self.http_host(),
      'http_method': method,
      'title': 'Mailpile dummy title',
      'csrf': self.csrf(),
      'name': session.config.get('my_from', {1: 'Chelsea Manning'}
                                 ).values()[0],
      'mailpile_size': idx and len(idx.INDEX) or 0
    }

    try:
      commands = UrlMap(session).map(self, method, path,
                                     query_data, post_data)
      results = [cmd.run() for cmd in commands]
      session.ui.display_result(results[-1])
    except UrlRedirectException, e:
      return self.send_http_redirect(e.url)
    except SuppressHtmlOutput:
      return
    except:
      e = traceback.format_exc()
      print e
      # FIXME: This may be a security risk?
      self.send_full_response(e, code=500, mimetype='text/plain')
      return None

    mimetype, content = session.ui.render_response(session.config)
    self.send_full_response(content, mimetype=mimetype)

  def do_PUT(self):
    return self.do_POST(method='PUT')

  def do_UPDATE(self):
    return self.do_POST(method='UPDATE')

  def do_HEAD(self):
    return self.do_GET(suppress_body=True, method='HEAD')

  def log_message(self, fmt, *args):
    self.server.session.ui.notify(self.server_url() + ' ' + (fmt % args))


class HttpServer(SocketServer.ThreadingMixIn, SimpleXMLRPCServer):
  def __init__(self, session, sspec, handler):
    SimpleXMLRPCServer.__init__(self, sspec, handler)
    self.session = session
    self.sessions = {}
    self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    self.sspec = (sspec[0] or 'localhost', self.socket.getsockname()[1])
    # FIXME: This could be more securely random
    self.secret = '-'.join([str(x) for x in [self.socket, self.sspec,
                                             time.time(), self.session]])

  def finish_request(self, request, client_address):
    try:
      SimpleXMLRPCServer.finish_request(self, request, client_address)
    except socket.error:
      pass
    if mailpile.util.QUITTING: self.shutdown()


class HttpWorker(threading.Thread):
  def __init__(self, session, sspec):
    threading.Thread.__init__(self)
    self.httpd = HttpServer(session, sspec, HttpRequestHandler)
    self.session = session

  def run(self):
    self.httpd.serve_forever()

  def quit(self):
    if self.httpd: self.httpd.shutdown()
    self.httpd = None


