# SPDX-FileCopyrightText: 2011-2015  Bjarni R. Einarsson, Mailpile ehf and friends
# SPDX-License-Identifier: AGPL-3.0-or-later

from mailpile.commands import Command

class maildeckCommand(Command):
           HTTP_CALLABLE = ('GET',)
