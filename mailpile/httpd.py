#!/usr/bin/python
#
# Mailpile's built-in HTTPD
#
###############################################################################
import socket
import SocketServer
from SimpleXMLRPCServer import SimpleXMLRPCServer, SimpleXMLRPCRequestHandler
from urlparse import parse_qs, urlparse

import mailpile.util
from mailpile.util import *
from mailpile.ui import Session, HtmlUI
from mailpile.commands import Action

global APPEND_FD_CACHE, APPEND_FD_CACHE_ORDER, APPEND_FD_CACHE_SIZE
global WORD_REGEXP, STOPLIST, BORING_HEADERS, DEFAULT_PORT

DEFAULT_PORT = 33411


class HttpRequestHandler(SimpleXMLRPCRequestHandler):

  PAGE_HEAD = """\
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml" lang="en"><head>
 <meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
 <script type='text/javascript'>
  function focus(eid) {var e = document.getElementById(eid);e.focus();
   if (e.setSelectionRange) {var l = 2*e.value.length;e.setSelectionRange(l,l)}
   else {e.value = e.value;}}
 </script>"""
  PAGE_LANDING_CSS = """\
 body {text-align: center; background: #f0fff0; color: #000; font-size: 2em; font-family: monospace; padding-top: 50px;}
 #heading a {text-decoration: none; color: #000;}
 #footer {text-align: center; font-size: 0.5em; margin-top: 15px;}
 #sidebar {display: none;}
 #search input {width: 170px;}"""
  PAGE_CONTENT_CSS = """\
 body {background: #f0fff0; font-family: monospace; color: #000;}
 body, div, form, h1, #header {padding: 0; margin: 0;}
 pre {display: inline-block; margin: 0 5px; padding: 0 5px;}
 #heading, #pile {padding: 5px 10px;}
 #heading {font-size: 3.75em; padding-left: 15px; padding-top: 15px; display: inline-block;}
 #heading a {text-decoration: none; color: #000;}
 #pile {z-index: -3; color: #666; font-size: 0.6em; position: absolute; top: 0; left: 0; text-align: center;}
 #search {display: inline-block;}
 #content {width: 80%; float: right;}
 #sidebar {width: 19%; float: left; overflow: hidden;}
 #sidebar .checked {font-weight: bold;}
 #sidebar ul.tag_list {list-style-type: none; white-space: nowrap; padding-left: 3em;}
 #sidebar .none {display: none;}
 #sidebar ul.tag_list input {position: absolute; margin: 0; margin-left: -1.5em;}
 #sidebar #sidebar_btns {display: inline-block; float: right;}
 #sidebar #sidebar_btns input {font-size: 0.8em; padding: 1px 2px; background: #d0dddd0; border: 1px solid #707770;}
 #sidebar #sidebar_btns input:hover {background: #e0eee0;}
 #footer {text-align: center; font-size: 0.8em; margin-top: 15px; clear: both;}
 p.rnav {margin: 4px 10px; text-align: center;}
 table.results {table-layout: fixed; border: 0; border-collapse: collapse; width: 100%; font-size: 13px; font-family: Helvetica,Arial;}
 tr.result td {overflow: hidden; white-space: nowrap; padding: 1px 3px; margin: 0;}
 tr.message td .message {white-space: pre-wrap; font-family: monospace;}
 tr.result td a {color: #000; text-decoration: none;}
 tr.result td a:hover {text-decoration: underline;}
 tr.result td.date a {color: #777;}
 tr.t_new {font-weight: bold;}
 #rnavtop {position: absolute; top: 0; right: 0;}
 td.date {width: 5em; font-size: 11px; text-align: center;}
 td.checkbox {width: 1.5em; text-align: center;}
 td.from {width: 25%; font-size: 12px;}
 td.tags {width: 12%; font-size: 11px; text-align: center;}
 tr.result td.tags a {color: #777;}
 tr.message td .headers {margin-top: 0px; font-size: 1.1em;}
 tr.message td .message .quote {color: #777;}
 tr.message td .message .pgpsign {color: #aaa; margin-bottom: -3px; margin-top: 3px;}
 tr.message td .message .pgptext {padding: 3px; margin: -3px; background: #ccf;}
 tr.odd {background: #ffffff;}
 tr.even {background: #eeeeee;}
 #qbox {width: 400px;}"""
  PAGE_BODY = """
</head><body onload='focus("qbox");'><div id='header'>
 <h1 id='heading'>
  <a href='/'>M<span style='font-size: 0.8em;'>AILPILE</span>!</a></h1>
 <div id='search'><form action='/'>
  <input id='qbox' type='text' size='100' name='q' value='%(lastq)s ' />
  <input type='hidden' name='csrf' value='%(csrf)s' />
 </form></div>
 <p id='pile'>to: from:<br />subject: email<br />@ to: subject: list-id:<br />envelope
  from: to sender: spam to:<br />from: search GMail @ in-reply-to: GPG bounce<br />
  subscribe 419 v1agra from: envelope-to: @ SMTP hello!</p>
</div>
<form id='actions' action='' method='post'>
<input type='hidden' name='csrf' value='%(csrf)s' /><div id='content'>"""
  PAGE_SIDEBAR = """\
</div><div id='sidebar'>
 <div id='sidebar_btns'>
  <input id='rm_tag_btn' type='submit' name='rm_tag' value='un-' title='Untag messages' />
  <input id='add_tag_btn' type='submit' name='add_tag' value='tag' title='Tag messages' />
 </div>"""
  PAGE_TAIL = """\
</div><p id='footer'>&lt;
 <a href='https://github.com/pagekite/Mailpile'>free software</a>
 by <a title='Bjarni R. Einarsson' href='http://bre.klaki.net/'>bre</a>
&gt;</p>
</form></body></html>"""

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
    self.wfile.write('HTTP/1.1 %s %s\r\n' % (code, msg))
    if code == 401:
      self.send_header('WWW-Authenticate',
                       'Basic realm=MP%d' % (time.time()/3600))
    self.send_header('Content-Length', len(message or ''))
    self.send_standard_headers(header_list=header_list, mimetype=mimetype)
    if not suppress_body:
      self.wfile.write(message or '')

  def csrf(self):
    ts = '%x' % int(time.time()/60)
    return '%s-%s' % (ts, b64w(sha1b64('-'.join([self.server.secret, ts]))))

  def render_page(self, body='', title=None, sidebar='', css=None,
                        variables=None):
    title = title or 'A huge pile of mail'
    variables = variables or {'lastq': '', 'path': '', 'csrf': self.csrf()}
    css = css or (body and self.PAGE_CONTENT_CSS or self.PAGE_LANDING_CSS)
    return '\n'.join([self.PAGE_HEAD % variables,
                      '<title>', title, '</title>',
                      '<style type="text/css">', css, '</style>',
                      self.PAGE_BODY % variables, body,
                      self.PAGE_SIDEBAR % variables, sidebar,
                      self.PAGE_TAIL % variables])

  def do_POST(self):
    (scheme, netloc, path, params, query, frag) = urlparse(self.path)
    if path.startswith('/::XMLRPC::/'):
      return SimpleXMLRPCRequestHandler.do_POST(self)

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
      body = 'POST geborked: %s' % e
      self.send_full_response(self.render_page(body=body,
                                               title='Internal Error'),
                              code=500)
      return None
    return self.do_GET(post_data=post_data)

  def do_HEAD(self):
    return self.do_GET(suppress_body=True)

  def parse_pqp(self, path, query_data, post_data, config):
    q = post_data.get('lq', query_data.get('q', ['']))[0].strip()

    cmd = ''
    if path.startswith('/_/'):
      cmd = ' '.join([path[3:], query_data.get('args', [''])[0]])
    elif path.startswith('/='):
      # FIXME: Should verify that the message ID matches!
      cmd = ' '.join(['view', path[1:].split('/')[0]])
    elif len(path) > 1:
      parts = path.split('/')[1:]
      if parts:
        fn = parts.pop()
        tid = self.server.session.config.get_tag_id('/'.join(parts))
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
    else:
      cmd = post_data.get('cmd', query_data.get('cmd', [cmd]))[0]

    return cmd.decode('utf-8')

  def do_GET(self, post_data={}, suppress_body=False):
    (scheme, netloc, path, params, query, frag) = urlparse(self.path)
    query_data = parse_qs(query)

    cmd = self.parse_pqp(path, query_data, post_data,
                         self.server.session.config)
    session = Session(self.server.session.config)
    session.ui = HtmlUI()
    index = session.config.get_index(session)

    if cmd:
      try:
        for arg in cmd.split(' /'):
          args = arg.strip().split()
          Action(session, args[0], ' '.join(args[1:]))
        body = session.ui.render_html()
        title = 'The biggest pile of mail EVAR!'
      except UsageError, e:
        body = 'Oops: %s' % e
        title = 'Ouch, too much mail, urgle, *choke*'
    else:
      body = ''
      title = None

    sidebar = ['<ul class="tag_list">']
    tids = index.config.get('tag', {}).keys()
    special = ['new', 'inbox', 'sent', 'drafts', 'spam', 'trash']
    def tord(k):
      tname = index.config['tag'][k]
      if tname.lower() in special:
        return '00000-%s-%s' % (special.index(tname.lower()), tname)
      return tname
    tids.sort(key=tord)
    for tid in tids:
      checked = ('tag:%s' % tid) in session.searched and ' checked' or ''
      checked1 = checked and ' checked="checked"' or ''
      tag_name = session.config.get('tag', {}).get(tid)
      tag_new = index.STATS.get(tid, [0,0])[1]
      sidebar.append((' <li id="tag_%s" class="%s">'
                      '<input type="checkbox" name="tag_%s"%s />'
                      ' <a href="/%s/">%s</a>'
                      ' <span class="tag_new %s">(<b>%s</b>)</span>'
                      '</li>') % (tid, checked, tid, checked1,
                                  tag_name, tag_name,
                                  tag_new and 'some' or 'none', tag_new))
    sidebar.append('</ul>')
    variables = {
      'lastq': post_data.get('lq', query_data.get('q',
                          [path != '/' and path[1] != '=' and path[:-1] or ''])
                             )[0].strip(),
      'csrf': self.csrf(),
      'path': path
    }
    self.send_full_response(self.render_page(body=body,
                                             title=title,
                                             sidebar='\n'.join(sidebar),
                                             variables=variables),
                            suppress_body=suppress_body)

  def log_message(self, fmt, *args):
    self.server.session.ui.notify(('HTTPD: '+fmt) % (args))


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


