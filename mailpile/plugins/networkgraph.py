# FIXME: This command is horribly slow, and demonstrates deficienies in
#        our current indexing. The search index needs to understand the
#        social graph natively so this, and other social queries, can be
#        fast.

import datetime
import re
import time

import mailpile.plugins
from mailpile.commands import Command
from mailpile.mailutils import Email, ExtractEmails
from mailpile.search import MailIndex
from mailpile.util import *

from mailpile.plugins.search import Search


class NetworkGraph(Search):

    """Get a graph of the network in the current search results."""
    ORDER = ('Searching', 1)

    class CommandResult(Command.CommandResult):
        pass

    def command(self, search=None):
        session, idx, start = self._do_search(search=search)

        nodes = []
        links = []
        res = {}

        for messageid in session.results:
            message = Email(self._idx(), messageid)
            try:
                msgfrom = ExtractEmails(message.get("from"))[0].lower()
            except IndexError, e:
                print "No e-mail address in '%s'" % message.get("from")
                continue

            msgto = [x.lower() for x in ExtractEmails(message.get("to"))]
            msgcc = [x.lower() for x in ExtractEmails(message.get("cc"))]
            msgbcc = [x.lower() for x in ExtractEmails(message.get("bcc"))]

            if msgfrom not in [m["email"] for m in nodes]:
                nodes.append({"email": msgfrom})

            for msgset in [msgto, msgcc, msgbcc]:
                for address in msgset:
                    if address not in [m["email"] for m in nodes]:
                        nodes.append({"email": address})

                curnodes = [x["email"] for x in nodes]
                fromid = curnodes.index(msgfrom)
                searchspace = [m for m in links if m["source"] == fromid]
                for recipient in msgset:
                    index = curnodes.index(recipient)
                    link = [m for m in searchspace if m["target"] == index]
                    if len(link) == 0:
                        links.append(
                            {"source": fromid, "target": index, "value": 1})
                    elif len(link) == 1:
                        link[0]["value"] += 1
                    else:
                        raise ValueError(
                            "Too many links! - This should never happen.")

            if len(nodes) >= 200:
                # Let's put a hard upper limit on how many nodes we can have, for performance reasons.
                # There might be a better way to do this though...
                res["limit_hit"] = True
                break

        res["nodes"] = nodes
        res["links"] = links
        res["searched"] = session.searched
        return res


mailpile.plugins.register_command('N', 'shownetwork',  NetworkGraph)
