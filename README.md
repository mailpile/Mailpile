# Welcome to Mailpile! #

Mailpile is a free-as-in-freedom personal e-mail searching and indexing
tool, largely inspired by Google's popular free e-mail service.  It wants
to eventually become a fast and flexible back-end for awesome personal
mail clients, probably webmail.


## Requirements ##

Mailpile is developed on a Debian 6 system, running:

   * Python 2.5
   * python-lxml 2.2.8

It might work with other versions. :-)

At the moment, you also need your e-mail to be in a traditional mbox
formatted Unix mailbox.


## Indexing your mail ##

The program `mailpile.py` expects to find a folder named `search` in the
current directory and symbolic links named `000` and `001` to whichever
two mailboxes you want indexed.  Omitting one is fine.  If you want more,
you'll have to Use The Source.

(In the future these things should all move to `$HOME/.mailpile` and
become more configurable, see the TODO list below.)

A simple test run might look like so:

    $ ln -s /var/spool/mail/YOURNAME 000
    $ mkdir search
    $ ./mailpile.py -r

The program prints details of its progress as it runs.  Note that just
opening the mailbox may take quite a while if it is large enough (it takes
about a bit over a minute to open my 500MB mailbox).  Stopping the program
with CTRL-C is nondestructive - it will save its progress and re-running
will continue the scan from where it left off.

### Huge mailboxes ###

If you are importing a very large amount of mail, it may be worth tweaking
the default size of the posting-lists (search term indexes) to avoid frequent
compactions and splits, both of which thrash the disk quite a bit:

    $ ./mailpile.py
    mailpile> set postinglist_kb = 10240
    mailpile> rescan
    ...

This will result in much slower searches, but once the mail has been imported
we can reset the limit and optimize the index:

    mailpile> unset postinglist_kb
    mailpile> optimize


## Basic use ##

At the moment `mailpile.py` only supports two commands, `rescan` (see
above) and `search`.  They may be abbreviated to just `r` or `s`, and
work both as command-line arguments and interactive commands.

The fun one is `search`:

    $ ./mailpile.py
    mailpile> search bjarni einarsson
    ...
    mailpile> search subject:bjarni
    ...
    mailpile> search from:bjarni to:somebody
    ...
    mailpile> s att:pdf
    ...
    mailpile> s has:attachment

The default search will search in message bodies, from lines, attachment
names and subjects.  Using the `to/from/subject/att` prefix will search
that part of the message only.  There's no way to *only* search bodies,
they're too full of crap anyway.  Adding terms narrows the search.

You can search from the command line with `mailpile.py -s term`,
but that will be rather slow because the metadata index has to be
loaded into RAM on each invocation.

(One of the TODOs is to change the command-line invocation to be
more shell-script friendly, which mostly would involve making the
output format more regular and machine readable.)


## A word on performance ##

Searching is all about disk seeks.

Mailpile tries to keep seeks to a minimum: any single-keyword search can
be answered by opening and parsing one relatively small file.  A single
search should take on the order of 200-400ms, depending on your filesystem
and hard drive.  Repeated searches or searches for closely related keywords
will be up to 10x faster, due to help from the OS cache.

This level of performance is possible, because all the metadata about the
messages themselves is kept in RAM.  This may seem extravagant, but on
modern computers you can actually handle massive amounts of e-mail this way.

Mailpile stores in RAM a little over 160 bytes of metadata per message
(actual size depends largely on the size of various headers), but Python
bloats that to about 1KB.  This means handling 100000 messages should
consume about 100MB of RAM, which isn't too bad if you consider how much
memory your browser (or desktop e-mail client) eats up.


## TODO ##

A random laundry list of things I haven't done yet and might accept
patches for:

   * Searchable dates (year:2010, month:12, day:24, date:2010-12-24)
   * Porperly sort the search results by date
   * A way to pageinate through search results
   * A more efficient incremental indexer
   * A way to view/extract messages/attachments
   * A way to assign/edit/remove tags (including read/unread/inbox)
   * Assign conversation IDs to messages (simplistic threading)
   * A way to create filters for auto-tagging messages
   * The ability to compose and send e-mail, and replies
   * Move everything to `$HOME/.mailpile` or a sane Windows alternative
   * Support for other mailbox formats, maybe even POP3/IMAP indexing
   * Meaningful settings and a way to load/save them
   * A shell scripting interface for automation
   * An XML-RPC interface to the search engine
   * A pretty UI on top of said XML-RPC interface

I am especially interested in help with UI work, I suck at that.

Note that Mailpile's emphasis is on *speed* and most of the features
above have already basic designs "in my head".  Chat with me on freenode
(I am BjarniRunar, and hang out on #pagekite) if you're interested in
my take on how to implement these things. Or just send a pull request! :-)


## Roadmap ##

This is the Mailpile roadmap:

   1. Write Python prototype for indexing and rapidly searching large
      volumes of e-mail. Define on-disk data formats.
   2. Add support for GMail-style conversation threading, tags and filters.
   3. Give it a very basic, ugly web interface, define an XML-RPC API.
   4. Look for some HTML/Javascript gurus who want to build a nice UI.
   5. Iterate until awesome.
   6. Rewrite search engine (using same data formats and same XML-RPC API)
      in C. If anyone cares - Python might be good enough.

Milestone 1 has been reached.


## Credits and License ##

Bjarni R. Einarsson <http://bre.klaki.net/> wrote this!  If you think
it's neat, you should also check out PageKite: <https://pagekite.net/>

Send me a patch: *your name here*

The GMail guys get mad props for creating the best webmail service out
there.  Wishing the Free Software world had something like it is what
inspired me to start working on this.

This program is free software: you can redistribute it and/or modify it
under the terms of the  GNU  Affero General Public License as published
by the Free Software Foundation, either version 3 of the License, or (at
your option) any later version.

