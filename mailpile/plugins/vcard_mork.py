#!/usr/bin/env python2.7
#coding:utf-8
from __future__ import print_function
import sys
import re
import getopt
from sys import stdin, stdout, stderr

from mailpile.i18n import gettext as _
from mailpile.i18n import ngettext as _n
from mailpile.plugins import PluginManager
from mailpile.vcard import *


_plugins = PluginManager(builtin=__file__)


def hexcmp(x, y):
    try:
        a = int(x, 16)
        b = int(y, 16)
        if a < b:
            return -1
        if a > b:
            return 1
        return 0

    except:
        return cmp(x, y)


class MorkImporter(VCardImporter):
    # Based on Demork by Mike Hoye <mhoye@off.net>
    # Which is based on Mindy by Kumaran Santhanam <kumaran@alumni.stanford.org>
    #
    # To understand the insanity that is Mork, read these:
    #  http://www-archive.mozilla.org/mailnews/arch/mork/primer.txt
    #  http://www.jwz.org/blog/2004/03/when-the-database-worms-eat-into-your-brain/
    #
    FORMAT_NAME = "Mork Database"
    FORMAT_DESCRPTION = "Thunderbird contacts database format."
    SHORT_NAME = "mork"
    CONFIG_RULES = {
        'filename': [_('Location of Mork database'), 'path', ""],
    }

    class Database:
        def __init__(self):
            self.cdict = {}
            self.adict = {}
            self.tables = {}

    class Table:
        def __init__(self):
            self.id = None
            self.scope = None
            self.kind = None
            self.rows = {}

    class Row:
        def __init__(self):
            self.id = None
            self.scope = None
            self.cells = []

    class Cell:
        def __init__(self):
            self.column = None
            self.atom = None

    def escapeData(self, match):
        return match.group() \
            .replace('\\\\n', '$0A') \
            .replace('\\)', '$29') \
            .replace('>', '$3E') \
            .replace('}', '$7D') \
            .replace(']', '$5D')

    pCellText = re.compile(r'\^(.+?)=(.*)')
    pCellOid = re.compile(r'\^(.+?)\^(.+)')
    pCellEscape = re.compile(r'((?:\\[\$\0abtnvfr])|(?:\$..))')
    pMindyEscape = re.compile('([\x00-\x1f\x80-\xff\\\\])')

    def escapeMindy(self, match):
        s = match.group()
        if s == '\\':
            return '\\\\'
        if s == '\0':
            return '\\0'
        if s == '\r':
            return '\\r'
        if s == '\n':
            return '\\n'
        return "\\x%02x" % ord(s)

    def encodeMindyValue(self, value):
        return self.pMindyEscape.sub(self.escapeMindy, value)

    backslash = {'\\\\': '\\',
                 '\\$': '$',
                 '\\0': chr(0),
                 '\\a': chr(7),
                 '\\b': chr(8),
                 '\\t': chr(9),
                 '\\n': chr(10),
                 '\\v': chr(11),
                 '\\f': chr(12),
                 '\\r': chr(13)}

    def unescapeMork(self, match):
        s = match.group()
        if s[0] == '\\':
            return self.backslash[s]
        else:
            return chr(int(s[1:], 16))

    def decodeMorkValue(self, value):
        m = self.pCellEscape.sub(self.unescapeMork, value)
        m = m.decode("utf-8")
        return m

    def addToDict(self, dict, cells):
        for cell in cells:
            eq = cell.find('=')
            key = cell[1:eq]
            val = cell[eq+1:-1]
            dict[key] = self.decodeMorkValue(val)

    def getRowIdScope(self, rowid, cdict):
        idx = rowid.find(':')
        if idx > 0:
            return (rowid[:idx], cdict[rowid[idx+2:]])
        else:
            return (rowid, None)

    def delRow(self, db, table, rowid):
        (rowid, scope) = self.getRowIdScope(rowid, db.cdict)
        if scope:
            rowkey = rowid + "/" + scope
        else:
            rowkey = rowid + "/" + table.scope

        if rowkey in table.rows:
            del table.rows[rowkey]

    def addRow(self, db, table, rowid, cells):
        row = self.Row()
        row.id, row.scope = self.getRowIdScope(rowid, db.cdict)

        for cell in cells:
            obj = self.Cell()
            cell = cell[1:-1]

            match = self.pCellText.match(cell)
            if match:
                obj.column = db.cdict[match.group(1)]
                obj.atom = self.decodeMorkValue(match.group(2))

            else:
                match = self.pCellOid.match(cell)
                if match:
                    obj.column = db.cdict[match.group(1)]
                    obj.atom = db.adict[match.group(2)]

            if obj.column and obj.atom:
                row.cells.append(obj)

        if row.scope:
            rowkey = row.id + "/" + row.scope
        else:
            rowkey = row.id + "/" + table.scope

        if rowkey in table.rows:
            print("ERROR: duplicate rowid/scope %s" % rowkey, file=stderr)
            print(cells, file=stderr)

        table.rows[rowkey] = row

    def inputMork(self, data):
        # Remove beginning comment
        pComment = re.compile('//.*')
        data = pComment.sub('', data, 1)

        # Remove line continuation backslashes
        pContinue = re.compile(r'(\\(?:\r|\n))')
        data = pContinue.sub('', data)

        # Remove line termination
        pLine = re.compile(r'(\n\s*)|(\r\s*)|(\r\n\s*)')
        data = pLine.sub('', data)

        # Create a database object
        db = self.Database()

        # Compile the appropriate regular expressions
        pCell = re.compile(r'(\(.+?\))')
        pSpace = re.compile(r'\s+')
        pColumnDict = re.compile(r'<\s*<\(a=c\)>\s*(?:\/\/)?\s*'
                                 '(\(.+?\))\s*>')
        pAtomDict = re.compile(r'<\s*(\(.+?\))\s*>')
        pTable = re.compile(r'\{-?(\d+):\^(..)\s*\{\(k\^(..):c\)'
                            '\(s=9u?\)\s*(.*?)\}\s*(.+?)\}')
        pRow = re.compile(r'(-?)\s*\[(.+?)((\(.+?\)\s*)*)\]')

        pTranBegin = re.compile(r'@\$\$\{.+?\{\@')
        pTranEnd = re.compile(r'@\$\$\}.+?\}\@')

        # Escape all '%)>}]' characters within () cells
        data = pCell.sub(self.escapeData, data)

        # Iterate through the data
        index = 0
        length = len(data)
        match = None
        tran = 0
        while True:
            if match:
                index += match.span()[1]
            if index >= length:
                break
            sub = data[index:]

            # Skip whitespace
            match = pSpace.match(sub)
            if match:
                index += match.span()[1]
                continue

            # Parse a column dictionary
            match = pColumnDict.match(sub)
            if match:
                m = pCell.findall(match.group())
                # Remove extraneous '(f=iso-8859-1)'
                if len(m) >= 2 and m[1].find('(f=') == 0:
                    m = m[1:]
                self.addToDict(db.cdict, m[1:])
                continue

            # Parse an atom dictionary
            match = pAtomDict.match(sub)
            if match:
                cells = pCell.findall(match.group())
                self.addToDict(db.adict, cells)
                continue

            # Parse a table
            match = pTable.match(sub)
            if match:
                id = match.group(1) + ':' + match.group(2)

                try:
                    table = db.tables[id]

                except KeyError:
                    table = self.Table()
                    table.id = match.group(1)
                    table.scope = db.cdict[match.group(2)]
                    table.kind = db.cdict[match.group(3)]
                    db.tables[id] = table

                rows = pRow.findall(match.group())
                for row in rows:
                    cells = pCell.findall(row[2])
                    rowid = row[1]
                    if tran and rowid[0] == '-':
                        rowid = rowid[1:]
                        self.delRow(db, db.tables[id], rowid)

                    if tran and row[0] == '-':
                        pass

                    else:
                        self.addRow(db, db.tables[id], rowid, cells)
                continue

            # Transaction support
            match = pTranBegin.match(sub)
            if match:
                tran = 1
                continue

            match = pTranEnd.match(sub)
            if match:
                tran = 0
                continue

            match = pRow.match(sub)
            if match and tran:
                # print >>stderr, ("WARNING: using table '1:^80' "
                #                  "for dangling row: %s") % match.group()
                rowid = match.group(2)
                if rowid[0] == '-':
                    rowid = rowid[1:]

                cells = pCell.findall(match.group(3))
                self.delRow(db, db.tables['1:80'], rowid)
                if row[0] != '-':
                    self.addRow(db, db.tables['1:80'], rowid, cells)
                continue

            # Syntax error
            print("ERROR: syntax error while parsing MORK file", file=stderr)
            print("context[%d]: %s" % (index, sub[:40]), file=stderr)
            index += 1

        # Return the database
        self.db = db
        return db

    def morkToHash(self):
        results = []
        columns = self.db.cdict.keys()
        columns.sort(hexcmp)

        tables = self.db.tables.keys()
        tables.sort(hexcmp)

        for table in [self.db.tables[k] for k in tables]:
            rows = table.rows.keys()
            rows.sort(hexcmp)
            for row in [table.rows[k] for k in rows]:
                email = name = ""
                result = {}
                for cell in row.cells:
                    result[cell.column] = cell.atom
                    if cell.column == "PrimaryEmail":
                        result["email"] = cell.atom.lower()
                    elif cell.column == "DisplayName":
                        result["name"] = cell.atom.strip("'")
                results.append(result)

        return results

    def load(self):
        with open(self.config.filename, "r") as fh:
            data = fh.read()

            if data.find("<mdb:mork") < 0:
                raise ValueError("Mork file required")

            self.inputMork(data)

    def get_vcards(self):
        self.load()
        people = self.morkToHash()
        # print people

        results = []
        vcards = {}
        for person in people:
            card = MailpileVCard()
            if "name" in person:
                card.add(VCardLine(name="FN", value=person["name"]))
            if "email" in person:
                card.add(VCardLine(name="EMAIL", value=person["email"]))
            results.append(card)

        return results


if __name__ == "__main__":
    import json
    filename = sys.argv[1]

    m = MorkImporter(filename=filename)
    m.load()
    print(m.get_contacts(data))
else:
    _plugins.register_vcard_importers(MorkImporter)
