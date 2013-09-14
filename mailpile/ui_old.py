# This file contains old code, left here so I can mine it for ideas - bre

from collections import defaultdict
import datetime
import os
import random
import re
import sys
import traceback
import json

from lxml.html.clean import autolink_html
import jsontemplate

import mailpile.commands
from mailpile.util import *
from mailpile.search import MailIndex


class xxBaseUI(object):

  def print_filters(self, config):
    w = int(self.WIDTH * 23/80)
    ffmt = ' %%3.3s %%-%d.%ds %%-%d.%ds %%s' % (w, w, w-2, w-2)
    self.say(ffmt % ('ID', ' Tags', 'Terms', ''))
    for fid, terms, tags, comment in config.get_filters(filter_on=None):
      self.say(ffmt % (
        fid,
        ' '.join(['%s%s' % (t[0], config['tag'].get(t[1:], t[1:]))
                  for t in tags.split()]),
        ((terms == '*') and '(all new mail)' or
         (terms == '@read') and '(read mail)' or terms or '(none)'),
        comment or '(none)'
      ))


class xxTextUI(xxBaseUI):
  def edit_messages(self, emails):
    for email in emails:
      try:
        if email.is_editable():
          es = email.get_editing_string().encode('utf-8')

          tf = tempfile.NamedTemporaryFile(suffix='.txt')
          tf.write(es)
          tf.flush()
          rv = subprocess.call(['edit', tf.name])
          tf.seek(0, 0)
          ns = tf.read()
          tf.close()

          if es != ns:
            email.update_from_string(ns)
            self.say('Message saved.  Use the "mail" command to send it.')
          else:
            self.warning('Message unchanged.')
        else:
          self.error('That message cannot be edited.')
      except:
        self.warning('Editing failed!')
        self.warning(traceback.format_exc())


class xxXmlUI(xxJsonUI):

  ROOT_NAME = 'xml'
  ROOT_ATTRS = {'testing': True}
  EXPLAIN_XML = True
  BARE_LISTS = False

  def esc(self, d):
    d = unicode(d)
    d = d.replace('&', '&amp;').replace('>', '&gt;').replace('<', '&lt;')
    return d.encode('utf-8')

  def render_xml_data(self, data, name='', attrs={}, indent=''):
    attrtext = ''
    if type(data) == type(dict()):
      data = self.render_xml_dict(data, indent=indent)+indent
      dtype = 'dict'
    elif type(data) == type(list()):
      data = self.render_xml_list(data, name=name, indent=indent)+indent
      dtype = 'list'
      if self.BARE_LISTS:
        return data
    elif type(data) == type(set()):
      data = self.render_xml_list(list(data), name=name, indent=indent)+indent
      dtype = 'set'
      if self.BARE_LISTS:
        return data
    else:
      data = self.esc(data)
      dtype = None
      if '\n' in data:
        attrtext += ' xml:space="preserve"'

    if self.EXPLAIN_XML:
      attrtext += dtype and (' type="%s"' % dtype) or ''
    for attr in attrs:
      attrtext += ' %s="%s"' % (attr, self.esc(attrs[attr]))

    if data.strip():
      return '%s<%s%s>%s</%s>' % (indent, name, attrtext, data, name)
    else:
      return '%s<%s%s/>' % (indent, name, attrtext)

  def render_xml_list(self, lst, name='items', indent=''):
    xml = ['']
    if name.endswith('s'):
      nh = name[:-1]
    else:
      nh = 'item'
    for item in lst:
      xml.append(self.render_xml_data(item, name=nh, indent=indent+' '))
    return '\n'.join(xml)+'\n'

  def render_xml_dict(self, dct, name='dict', indent=''):
    xml = ['']
    for name in dct.keys():
      xml.append(self.render_xml_data(dct[name], name=name, indent=indent+' '))
    return '\n'.join(xml)+'\n'

  def render_data(self, session, request_url, request_path):
    message = ('<?xml version="1.0"?>\n' +
               self.render_xml_data(self.buffered_json,
                                    name=self.ROOT_NAME,
                                    attrs=self.ROOT_ATTRS))
    return message, 'text/xml'


class xxRssUI(xxXmlUI):

  ROOT_NAME = 'rss'
  ROOT_ATTRS = {'version': '2.0'}
  EXPLAIN_XML = False
  BARE_LISTS = True

  def clear(self):
    xxXmlUI.clear(self)
    self.buffered_json = {
      "channel": {'items': self.buffered_results}
    }

  def explain_msg_summary(self, info):
    summary = xxXmlUI.explain_msg_summary(self, info)
    return {
      '_id': summary['id'],
      'title': summary['subject'],
      'link': summary['url'],
      'pubDate': summary['date']
    }

  def prune_message_tree(self, tree):
    r = {}
    r['items'] = [self.explain_msg_summary(c) for c in tree['conversation']]
    for item in r['items']:
      if item['_id'] == tree['id']:
        item['description'] = 'FIXME: Insert text body here, w/o quotes?'
    return r

  def render_data(self, session, request_url, request_path):
    # Reparent conversation list for single message
    if (len(self.buffered_results) > 0
    and 'items' in self.buffered_results[0]):
      self.buffered_results = self.buffered_results[0]['items']
      self.buffered_json['channel']['items'] = self.buffered_results

    # Make URLs absolute
    for item in self.buffered_results:
      item['link'] = '%s%s' % (request_url, item['link'])

    # Cleanup...
    for r in self.buffered_results:
      if 'tags' in r: del r['tags']
      if '_id' in r: del r['_id']

    # FIXME: Add channel info to buffered_json before rendering.

    return (xxXmlUI.render_data(self, session, request_url, request_path)[0],
            'application/rss+xml')


class xxHtmlUI(xxHttpUI):
  WIDTH = 110

  def __init__(self, request):
    xxHttpUI.__init__(self, request)
    self.buffered_html = []
    self.request = request

  def clear(self):
    self.buffered_html = []

  def say(self, text='', newline='\n', fd=None):
    # Just suppress the progress indicator chitter chatter
    if not text.endswith('\r'):
      self.buffered_html.append(('text', text+newline))

  def fmt(self, l):
    return l[1].replace('&', '&amp;').replace('>', '&gt;').replace('<', '&lt;')

  def transform_text(self):
    text = [self.fmt(l) for l in self.buffered_html if l[0] != 'html']
    self.buffered_html = [l for l in self.buffered_html if l[0] == 'html']
    self.buffered_html.append(('html', '<pre id="loglines">%s</pre>' % ''.join(text)))

  def render(self, session, request_url, path):
    config = session.config
    index = config.get_index(session)
    sidebar = ['<ul class="tag_list">']
    tids = config.get('tag', {}).keys()
    special = ['new', 'inbox', 'sent', 'drafts', 'spam', 'trash']
    def tord(k):
      tname = config['tag'][k]
      if tname.lower() in special:
        return '00000-%s-%s' % (special.index(tname.lower()), tname)
      return tname
    tids.sort(key=tord)
    for tid in tids:
      checked = ('tag:%s' % tid) in session.searched and ' checked' or ''
      checked1 = checked and ' checked="checked"' or ''
      tag_name = config.get('tag', {}).get(tid)
      tag_new = index.STATS.get(tid, [0,0])[1]
      sidebar.append((' <li id="tag_%s" class="%s">'
                      '<input type="checkbox" name="tag_%s"%s />'
                      ' <a href="/%s/">%s</a>'
                      ' <span class="tag_new %s">(<b>%s</b>)</span>'
                      '</li>') % (tid, checked, tid, checked1,
                                  tag_name, tag_name,
                                  tag_new and 'some' or 'none', tag_new))
    sidebar.append('</ul>')
    lastqpath = (path != '/' and path[1] not in ('=', '_') and path[:-1]
                 or '')
    variables = {
      'url': request_url,
      'lastq': self.post_data.get('lq', self.query_data.get('q',
                                  [lastqpath]))[0].strip().decode('utf-8'),
      'csrf': self.request.csrf(),
      'path': path
    }

    # FIXME: This title is dumb
    title = 'The biggest pile of mail EVAR!'

    self.request.send_full_response(self.render_page(config, variables,
                                                    title=title,
                                                   body=self.render_html(),
                                                  sidebar='\n'.join(sidebar)),
                                    suppress_body=False)

  def render_page(self, config, variables, body='', title='', sidebar=''):
    tpl = config.get('path', {}).get(self.request.http_host(), 'html_template')
    def r(part):
      return config.open_file(tpl, 'html/%s.html' % part)[1].read() % variables
    return ''.join([
      r('head'), '<title>', title, '</title>',
      r('body'), body,
      r('sidebar'), sidebar,
      r('tail')
    ])


  def render_html(self):
    self.transform_text()
    html = ''.join([l[1] for l in self.buffered_html])
    self.buffered_html = []
    return html

  def display_results(self, idx, results, terms,
                            start=0, end=None, num=None,
                            expand=None, fd=None):
    if not results: return (0, 0)

    num = num or 50
    if end: start = end - num
    if start > len(results): start = len(results)
    if start < 0: start = 0

    count = 0
    nav = []
    if start > 0:
      bstart = max(1, start-num+1)
      nav.append(('<a href="/?q=/search%s %s">&lt;&lt; page back</a>'
                  ) % (bstart > 1 and (' @%d' % bstart) or '', ' '.join(terms)))
    else:
      nav.append('first page')
    nav.append('(about %d results)' % len(results))
    if start+num < len(results):
      nav.append(('<a href="/?q=/search @%d %s">next page &gt;&gt;</a>'
                  ) % (start+num+1, ' '.join(terms)))
    else:
      nav.append('last page')
    self.buffered_html.append(('html', ('<p id="rnavtop" class="rnav">%s &nbsp;'
                                        ' </p>\n') % ' '.join(nav)))

    self.buffered_html.append(('html', '<table class="results" id="results">\n'))
    expand_ids = [e.msg_idx for e in (expand or [])]
    for mid in results[start:start+num]:
      count += 1
      try:
        msg_info = idx.get_msg_by_idx(mid)

        all_msg_tags = [idx.config['tag'].get(t,t)
                        for t in idx.get_tags(msg_info=msg_info)]
        msg_tags = sorted([t for t in all_msg_tags
                           if 'tag:%s' % t not in terms])
        tag_classes = ['t_%s' % t.replace('/', '_') for t in msg_tags]
        msg_tags = ['<a href="/%s/">%s</a>' % (t, re.sub("^.*/", "", t))
                    for t in msg_tags]

        if expand and mid in expand_ids:
          self.buffered_html.append(('html', (' <tr class="result message %s">'
            '<td valign=top class="checkbox"><input type="checkbox" name="msg_%s" /></td>'
            '<td valign=top class="message" colspan=2>\n'
          ) % (
            (count % 2) and 'odd' or 'even',
            msg_info[idx.MSG_IDX],
          )))
          self.display_messages([expand[expand_ids.index(mid)]],
                                context=False, fd=fd, sep='');
          self.transform_text()

          msg_date = datetime.date.fromtimestamp(int(msg_info[idx.MSG_DATE], 36))
          self.buffered_html.append(('html', (
            '</td>'
            '<td valign=top class="tags">%s</td>'
            '<td valign=top class="date"><a href="?q=date:%4.4d-%d-%d">%4.4d-%2.2d-%2.2d</a></td>'
          '</tr>\n') % (
            ', '.join(msg_tags),
            msg_date.year, msg_date.month, msg_date.day,
            msg_date.year, msg_date.month, msg_date.day
          )))
        else:
          msg_subj = msg_info[idx.MSG_SUBJECT] or '(no subject)'

          if expand:
            msg_from = [msg_info[idx.MSG_FROM]]
            msg_date = [msg_info[idx.MSG_DATE]]
          else:
            conversation = idx.get_conversation(msg_info)
            msg_from = [r[idx.MSG_FROM] for r in conversation]
            msg_date = [r[idx.MSG_DATE] for r in conversation]

          msg_date = datetime.date.fromtimestamp(max([
                                                 int(d, 36) for d in msg_date]))

          edit = ('Drafts' in all_msg_tags) and 'edit.html' or ''
          self.buffered_html.append(('html', (' <tr class="result %s %s">'
            '<td class="checkbox"><input type="checkbox" name="msg_%s" /></td>'
            '<td class="from"><a href="/=%s/%s/%s">%s</a></td>'
            '<td class="subject"><a href="/=%s/%s/%s">%s</a></td>'
            '<td class="tags">%s</td>'
            '<td class="date"><a href="?q=date:%4.4d-%d-%d">%4.4d-%2.2d-%2.2d</a></td>'
          '</tr>\n') % (
            (count % 2) and 'odd' or 'even', ' '.join(tag_classes).lower(),
            msg_info[idx.MSG_IDX],
            msg_info[idx.MSG_IDX], msg_info[idx.MSG_ID], edit,
            self._compact(self._names(msg_from), 30),
            msg_info[idx.MSG_IDX], msg_info[idx.MSG_ID], edit,
            msg_subj,
            ', '.join(msg_tags),
            msg_date.year, msg_date.month, msg_date.day,
            msg_date.year, msg_date.month, msg_date.day,
          )))
      except (IndexError, ValueError):
        pass
    self.buffered_html.append(('html', '</table>\n'))
    self.buffered_html.append(('html', ('<p id="rnavbot" class="rnav">%s &nbsp;'
                                        ' </p>\n') % ' '.join(nav)))
    self.mark(('Listed %d-%d of %d results'
               ) % (start+1, start+count, len(results)))
    return (start, count)

  def display_message(self, email, tree, raw=False, sep='', fd=None):
    if raw:
      for line in email.get_file().readlines():
        try:
          line = line.decode('utf-8')
        except UnicodeDecodeError:
          try:
            line = line.decode('iso-8859-1')
          except:
            line = '(MAILPILE DECODING FAILED)\n'
        self.say(line, newline='', fd=fd)
    else:
      self.buffered_html.append(('html', '<div class=headers>'))
      for hdr in ('From', 'Subject', 'To', 'Cc'):
        value = email.get(hdr, '')
        if value:
          html = '<b>%s:</b> %s<br>' % (hdr, escape_html(value))
          self.buffered_html.append(('html', html))
      self.buffered_html.append(('html', '</div><br>'))

      if tree['text_parts']:
        self.buffered_html.append(('html', '<div class="message plain">'))
        last = '<bogus>'
        for part in tree['text_parts']:
          if part['data'] != last:
            self.buffered_html.append(self.fmt_part(part))
            last = part['data']
      else:
        self.buffered_html.append(('html', '<div class="message html">'))
        last = '<bogus>'
        for part in tree['html_parts']:
          if part['data'] != last:
            self.buffered_html.append(('html', autolink_html(part['data'])))
            last = part['data']
      if tree['attachments']:
        self.buffered_html.append(('html', '</div><div class="attachments"><ul>'))
        for att in tree['attachments']:
          desc = ('<a href="./att:%(count)s">Attachment: %(filename)s</a> '
                  '(%(mimetype)s, %(length)s bytes)') % att
          self.buffered_html.append(('html', '<li>%s</li>' % desc))
        self.buffered_html.append(('html', '</ul>'))
      self.buffered_html.append(('html', '</div>'))

  def fmt_part(self, part):
    what = [part['type'], escape_html(part['data'])]
    if what[0] == 'pgpbeginsigned':
      what[1] = ('<input type="submit" name="gpg_recvkey"'
                 ' value="Get PGP key and Verify">' + what[1])
    if what[0] in ('pgpsignature', 'pgpbeginsigned'):
      key_id = re.search('key ID ([0-9A-Fa-f]+)', what[1])
      if key_id:
        what[1] += ('<input type="hidden" name="gpg_key_id" value="0x%s">'
                    ) % key_id.group(1)

    return ('html', autolink_html('<p class="%s">%s</p>' % tuple(what)))

  def edit_messages(self, emails):
    for email in emails:
      if email.is_editable():
        es = email.get_editing_string()
        save_id = len(self.buffered_html)
        self.buffered_html.append(('html',
                                   '<div class=editing>'
                            '<input type=hidden name="save_%d_msg" value="%s">'
                              '<textarea name="@save_%d_data" cols=72 rows=20>'
                                   '' % (save_id, email.msg_mid(), save_id)))
        self.buffered_html.append(('html', escape_html(es)))
        self.buffered_html.append(('html', '</textarea><br>'
                                '<input type=submit name="save_%d" value=Save>'
                                '<input type=submit name="mail_%d" value=Send>'
                                           '</div>' % (save_id, save_id)))
      else:
        self.error('That message cannot be edited.')

  def display_vcard(self, vcard, compact=False):
    if compact:
      self.say('%s' % vcard)
    else:
      self.buffered_html.append(('html',
                        '<pre>%s</pre>' % escape_html(vcard.as_vCard())))



