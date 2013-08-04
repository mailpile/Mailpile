#!/usr/bin/env python2.7
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
    # FIXME: Do we need more security checks?
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
      r = self.server.session.ui.render_page(config,
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

    data = {}
    cmd = ''
    if path.startswith('/_/'):
      cmd = path[3:].replace('/', ' ').replace('.json', '').replace('.jhtml', '').replace('.xml', '')
      cmd += ' ' + query_data.get('args', [''])[0]
    elif path.startswith('/='):
      parts = path.split('/')
      if len(parts) == 4:
        msg_idx = parts[1]
        if parts[3] in ('', 'message.xml', 'message.json', 'message.rss'):
          cmd = ' '.join(['view', msg_idx])
        elif parts[3] == 'edit.html':
          edit_key = '@edit_'+msg_idx[1:]
          if edit_key in post_data:
            cmd = ' '.join(['update', msg_idx, edit_key])
          else:
            cmd = ' '.join(['compose', msg_idx])
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
        if parts[3] in ('inline', 'inline-preview', 'preview', 'download'):
          cmd = ' '.join(['extract', parts[3], '#%s' % parts[4], parts[1]])

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

    # Default command/argument processing.
    cmd = post_data.get('cmd', query_data.get('cmd', [cmd]))[0]
    for pd in post_data:
      if pd.startswith('@'):
        data[pd] = post_data[pd][0]

    # Explicit support for a few particular commands
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
    if 'gpg_recvkey' in post_data:
      cmd = 'gpgrecv %s /%s' % (post_data.get('gpg_key_id')[0], cmd)
    for pd in post_data:
      if pd.startswith('save_') or pd.startswith('mail_'):
        try:
          pid = int(pd[5:])
          msg_idx = post_data.get('save_%d_msg' % pid)[0]
          if cmd.startswith('compose'):
            cmd = 'compose =%s' % msg_idx
          if pd.startswith('mail_'):
            cmd = 'mail =%s /%s' % (msg_idx, cmd)
          cmd = 'update =%s @save_%d_data /%s' % (msg_idx, pid, cmd)
        except ValueError:
          pass

    return cmd.strip(), data

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

    if not path or path == '/' and not query:
      # FIXME: This should probably be a login page of some sort.
      path = '/Inbox/'

    session.ui = HttpUserInteraction(self)

    # We peek at the ending to configure the UI, but any further parsing of
    # the path and arguments takes place in parse_pqp.
    if path.endswith('.json'):    session.ui.render_mode = 'json'
    elif path.endswith('.jhtml'): session.ui.render_mode = 'jhtml'
    elif path.endswith('.xml'):   session.ui.render_mode = 'xml'
    elif path.endswith('.rss'):   session.ui.render_mode = 'rss'
    elif path.endswith('.txt'):   session.ui.render_mode = 'text'
    else:                         session.ui.render_mode = 'html'

    try:
      cmd, data = self.parse_pqp(path, query_data, post_data, config)
      session.ui.html_variables = {
        'title': 'Mailpile dummy title',
        'csrf': 'FIXMEFIXME',
        'name': session.config.get('my_from', {1: 'Bradley Manning'}
                                   ).values()[0],
        'mailpile_size': len(session.config.index.INDEX)
      }
      if cmd:
        for arg in cmd.split(' /'):
          args = arg.strip().split()
          result = Action(session, args[0], ' '.join(args[1:]), data=data)
          session.ui.display_result(result)
    except UsageError, e:
      session.ui.error('%s' % e)
    except SuppressHtmlOutput:
      return

    mimetype, content = session.ui.render_response(session.config)
    self.send_full_response(content, mimetype=mimetype)

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


