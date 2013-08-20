
import datetime
import re
import time

import mailpile.plugins
from mailpile.commands import Command
from mailpile.mailutils import Email, ExtractEmails
from mailpile.search import MailIndex
from mailpile.util import *

from mailpile.plugins.search import Search



class NetworkGraph(Command):
  """Get a graph of the network in the current search results."""
  ORDER = ('Searching', 1)

  def command(self):
    nodes = []
    links = []

    session, idx = self.session, self._idx()

    if len(self.args) > 0:
      print "Got args. Running search."
      for arg in self.args:
        if ':' in arg or (arg and arg[0] in ('-', '+')):
          session.searched.append(arg.lower())
        else:
          session.searched.extend(re.findall(WORD_REGEXP, arg.lower()))
      session.results = list(idx.search(session, session.searched))
      idx.sort_results(session, session.results, how=session.order)
      print session.results

    for messageid in session.results:
      message = Email(self._idx(), messageid)
      try:
        msgfrom = ExtractEmails(message.get("from"))[0]
      except IndexError, e:
        print "No e-mail address in '%s'" % message.get("from")
        continue

      msgto = ExtractEmails(message.get("to"))
      msgcc = ExtractEmails(message.get("cc"))
      msgbcc = ExtractEmails(message.get("bcc"))

      if msgfrom not in [m["email"] for m in nodes]:
        nodes.append({"email": msgfrom})

      for msgset, msgtype  in ((msgto, "to"), (msgcc, "cc"), (msgbcc, "bcc")):
        for address in msgset:
          if address not in [m["email"] for m in nodes]:
            nodes.append({"email": address})

        fromid = [x["email"] for x in nodes].index(msgfrom)
        searchspace = [m for m in links if m["source"] == fromid and m["type"] == msgtype]
        for recipient in msgset:
          index = [x["email"] for x in nodes].index(recipient)
          link = [m for m in searchspace if m["target"] == index]
          if len(link) == 0:
            links.append({"source": fromid, "target": index, "type": msgtype, "weight": 1})
          elif len(link) == 1:
            link[0]["weight"] += 1
          else:
            raise ValueError("Too many links! - This should never happen.")

    return {"nodes": nodes, "links": links, "searched": session.searched}


mailpile.plugins.register_command('N', 'shownetwork',  NetworkGraph)