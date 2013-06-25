#!/usr/bin/python
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
from mailpile.util import *
from mailpile.ui import *
from mailpile.commands import Action

global APPEND_FD_CACHE, APPEND_FD_CACHE_ORDER, APPEND_FD_CACHE_SIZE
global WORD_REGEXP, STOPLIST, BORING_HEADERS, DEFAULT_PORT

DEFAULT_PORT = 33411


class HttpRequestHandler(SimpleXMLRPCRequestHandler):

  def http_host(self):
    return self.headers.get('host', 'localhost').rsplit(':', 1)[0]

  def server_url(self):
    return '%s://%s' % (self.headers.get('x-forwarded-proto', 'http'),
                        self.headers.get('host', 'localhost'))

  def send_http_response(self, code, msg):
    self.wfile.write('HTTP/1.1 %s %s\r\n' % (code, msg))

  def send_standard_headers(self, header_list=[],
                            cachectrl='private', mimetype='text/html'):
    if mimetype.startswith('text/') and ';' not in mimetype:
      mimetype += ('; charset=utf-8')
    self.send_header('Cache-Control', cachectrl)
    self.send_header('Content-Type', mimetype)
    for header in header_list:
      self.send_header(header[0], header[1])
    self.end_headers()

  def send_full_response(self, message, code=200, msg='OK', mimetype='text/html',
                         header_list=[], suppress_body=False):
    message = unicode(message).encode('utf-8')
    self.log_request(code, message and len(message) or '-')
    self.send_http_response(code, msg)
    if code == 401:
      self.send_header('WWW-Authenticate',
                       'Basic realm=MP%d' % (time.time()/3600))
    self.send_standard_headers(header_list=header_list + [
                                 ('Content-Length', len(message or ''))
                               ],
                               mimetype=mimetype,
                               cachectrl="no-cache")
    if not suppress_body:
      self.wfile.write(message or '')

  def send_file(self, config, filename):
    # Needs more checking
    if '..' in filename:
      code, msg = 403, "Access denied"
    else:
      try:
        tpl = config.get('path', {}).get(self.http_host(), 'html_template')
        fpath, fd = config.open_file(tpl, filename)
        mimetype = mimetypes.guess_type(fpath)[0] or "application/octet-stream"
        message = fd.read()
        code, msg = 200, "OK"
      except IOError, e:
        if e.errno == 2:
          code, msg = 404, "File not found"
        elif e.errno == 13:
          code, msg = 403, "Access denied"
        else:
          code, msg = 500, "Internal server error"
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
    ts = '%x' % int(time.time()/60)
    return '%s-%s' % (ts, b64w(sha1b64('-'.join([self.server.secret, ts]))))

  def do_POST(self):
    (scheme, netloc, path, params, query, frag) = urlparse(self.path)
    if path.startswith('/::XMLRPC::/'):
      return SimpleXMLRPCRequestHandler.do_POST(self)

    config = self.server.session.config
    post_data = { }
    try:
      clength = int(self.headers.get('content-length'))
      ctype, pdict = cgi.parse_header(self.headers.get('content-type'))
      if ctype == 'multipart/form-data':
        post_data = cgi.parse_multipart(self.rfile, pdict)
      elif ctype == 'application/x-www-form-urlencoded':
        if clength > 5*1024*1024:
          raise ValueError('OMG, input too big')
        post_data = cgi.parse_qs(self.rfile.read(clength), 1)
      else:
        raise ValueError('Unknown content-type')

    except (IOError, ValueError), e:
      r = HtmlUI(self).render_page(config,
                                   {'lastq': '', 'csrf': '', 'path': ''},
                                   body='POST geborked: %s' % e,
                                   title='Internal Error')
      self.send_full_response(r, code=500)
      return None
    return self.do_GET(post_data=post_data)

  def do_HEAD(self):
    return self.do_GET(suppress_body=True)

  def parse_pqp(self, path, query_data, post_data, config):
    q = post_data.get('lq', query_data.get('q', ['']))[0].strip().decode('utf-8')

    cmd = ''
    if path.startswith('/_/'):
      cmd = path[3:].replace('.json', '').replace('.xml', '') + ' '
      cmd += query_data.get('args', [''])[0]
    elif path.startswith('/='):
      parts = path.split('/')
      if len(parts) == 4:
        msg_idx = parts[1]
        if parts[3] in ('', 'message.xml', 'message.json', 'message.rss'):
          cmd = ' '.join(['view', msg_idx])
        elif parts[3] == 'message.eml':
          cmd = ' '.join(['view', 'raw', msg_idx])
        if parts[3].lower().startswith('cid:'):
          cmd = ' '.join(['extract', '<%s>' % parts[3][4:], msg_idx])
        elif parts[3].lower().startswith('att:'):
          cmd = ' '.join(['extract', '#%s' % parts[3][4:], msg_idx])
        else:
          # bogus?
          pass
      elif len(parts) == 6:
        pass

    elif len(path) > 1:
      parts = path.split('/')[1:]
      if parts:
        fn = parts.pop()
        tid = config.get_tag_id('/'.join(parts))
        if tid:
          if q and q[0] != '/':
            q = 'tag:%s %s' % (tid, q)
          elif not q:
            q = 'tag:%s' % tid

    if q:
      if q[0] == '/':
        cmd = q[1:]
      else:
        tag = ''
        cmd = ''.join(['search ', tag, q])

    if 'add_tag' in post_data or 'rm_tag' in post_data:
      if 'add_tag' in post_data:
        fmt = 'tag +%s %s /%s'
      else:
        fmt = 'tag -%s %s /%s'
      msgs = ['='+k[4:] for k in post_data if k.startswith('msg_')]
      if msgs:
        for tid in [k[4:] for k in post_data if k.startswith('tag_')]:
          tname = config.get('tag', {}).get(tid)
          if tname:
            cmd = fmt % (tname, ' '.join(msgs), cmd)
    elif 'gpg_recvkey' in post_data:
      cmd = 'gpgrecv %s /%s' % (post_data.get('gpg_key_id')[0], cmd)
    else:
      cmd = post_data.get('cmd', query_data.get('cmd', [cmd]))[0]

    return cmd.strip()

  def do_GET(self, post_data={}, suppress_body=False):
    (scheme, netloc, path, params, query, frag) = urlparse(self.path)
    query_data = parse_qs(query)
    path = unquote(path)

    # HTTP is stateless, so we create a new session for each request.
    config = self.server.session.config
    session = Session(config)

    if path == "/favicon.ico":
      path = "/_/static/favicon.ico"
    if path.startswith("/_/static/"):
      return self.send_file(config, path.split("/_/static/", 1)[1])

    restype = 'html'
    if not path or path == '/':
      # FIXME: This should probably be a login page of some sort.
      path = '/Inbox/'

    # We peek at the ending to select a UI, but any further parsing of the
    # path and arguments takes place in parse_pqp.
    if path.endswith('.json'):
      session.ui = JsonUI(self)
    elif path.endswith('.xml'):
      session.ui = XmlUI(self)
    elif path.endswith('.rss'):
      session.ui = RssUI(self)
    else:
      session.ui = HtmlUI(self)

    session.ui.set_postdata(post_data)
    session.ui.set_querydata(query_data)
    try:
      cmd = self.parse_pqp(path, query_data, post_data, config)
      if cmd:
        for arg in cmd.split(' /'):
          args = arg.strip().split()
          Action(session, args[0], ' '.join(args[1:]))

    except UsageError, e:
      session.ui.error('%s' % e)
    except SuppressHtmlOutput:
      return

    session.ui.render(session, self.server_url(), path)

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


