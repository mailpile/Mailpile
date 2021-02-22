# SPDX-FileCopyrightText: 2011-2015  Bjarni R. Einarsson, Mailpile ehf and friends
# SPDX-License-Identifier: AGPL-3.0-or-later

import sys
from mailpile.app import Main


def main():
    Main(sys.argv[1:])


if __name__ == "__main__":
    main()
