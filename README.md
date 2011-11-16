# Welcome to Mailpile! #

Mailpile is a free-as-in-freedom personal e-mail searching and indexing
tool, largely inspired by Google's popular proprietary-but-gratis e-mail
service.  It wants to eventually become a fast and flexible back-end
for awesome personal mail clients, including webmail.

**WARNING:**  Mailpile is still experimental and isn't actually very useful
yet.  It'll tell you that you have mail matching a given search and let
you sort it and browse the subjects... but it won't help you actually read
or write any mail.  If you are looking for a useful tool right now, you
should probably check back in a couple of weeks.


## Requirements ##

Mailpile is developed on a Debian 6 system, running:

   * Python 2.6
   * python-lxml 2.2.8

It might work with other versions. :-)

At the moment, you also need your e-mail to be in a traditional mbox
formatted Unix mailbox.


## Indexing your mail ##

The program `mailpile.py` will create and use a folder in your home
directory named `.mailpile` for its indexes and settings.

A simple test run might look like so:

    $ ./mailpile.py -A /var/spool/mail/YOURNAME -R

The program prints details of its progress as it runs.  Note that just
opening the mailbox may take quite a while if it is large enough (it takes
about a bit over a minute to open my 500MB mailbox).  Stopping the program
with CTRL-C is (relatively) nondestructive - it will try to save its
progress and re-running should continue the scan from where it left off.


## Basic use ##

The most important command `mailpile.py` supports is the `search` command.
The second most important is probably `help`. :-)

All commands can be abbreviated to only their first character (the less
commonly used commands use capital letters for this).

### Searching ###

Some searching examples:

    $ ./mailpile.py
    mailpile> search bjarni einarsson
    ...
    mailpile> search subject:bjarni
    ...
    mailpile> search from:bjarni to:somebody
    ...
    mailpile> search from:bjarni -from:pagekite
    ...
    mailpile> s att:pdf
    ...
    mailpile> s has:attachment
    ...
    mailpile> s date:2011-1-30 +date:2011-1-29
    ...
    mailpile> s year:2011 month:12
    ...

The default search will search in message bodies, from lines, attachment
names and subjects.  Using a `to/from/subject/att/...` prefix will
search that part of the message only.  There's no way to *only* search
bodies, they're too full of crap anyway.

Adding terms narrows the search, unless the extra terms are prefixed with
a `+`, then results are combined.  Prefixing with `-` removes matches for
that term instead.

You can paginate through results using `next` and `previous`.

To view a message, use the `view` command with the number of the result
or one of the magic words `all` or `these`:

    mailpile> search year:2011 month:12
    ...
    mailpile> view 1 2 6
    ...

(Mailpile currently assumes you have `less` installed and in your path for
viewing e-mail. This is a temporary hack.)

You can also search from the command line with `mailpile.py -s term`,
but that will be a bit slower because the metadata index has to be
loaded into RAM on each invocation.


### Sorting the results ###

The `order` command lets you sort results.  Available sort orders
are: `index`, `random`, `date`, `from` and `subject`.  Threading
may be disabled by prefixing the order with `flat-`, and the order
may be reversed by further prefixing it with `rev-`.  Examples:

    mailpile> order rev-subject    # Reverse subject order
    ...
    mailpile> order rev-flat-date  # Flat reverse date order
    ...
    mailpile> order                # Default sort order
    ...

You can also change the default sort order by using the `order`
setting:

    mailpile> set order = rev-flat-date  # Change default order
    ...
    mailpile> unset order                # Use program defaults
    ...


### Tags and filters ###

Mailpile allows you to create tags and attach any number of tags to each
message.  For example:

    mailpile> addtag Inbox
    ...
    mailpile> search to:bre from:klaki
    ...
    mailpile> tag +Inbox all
    ...
    mailpile> inbox
    ...

The `tag` command accepts a single tag name, prefixed with a `+` or `-`
(for adding or removing the tag), followed by a description of messages.
The message description can be:

  * `all` will affect all messages
  * `these` will affect currently listed messages
  * A list of numbers or ranges (`1 2 3 5-10 15`)

All these are relative to the last search, so `1` is the first result
of the most recent search and `all` would be all matching messages.

Tags names are themselves recognized as specialized search commands in
the `mailpile` CLI.

If you want Mailpile to automatically tag (or untag) messages based on
certain search criteria, you can use the `filter` command instead:

    mailpile> addtag Lists/Diaspora
    ...
    mailpile> search list:diaspora
    ...
    mailpile> filter +lists/diaspora -inbox Diaspora Mail
    ...

This will tag all the search results and then apply the same rules as
new messages are received.

Filters are always processed in a fixed order, so even if one filter
adds a tag, a subsequent one may remove it again.  This allows you to
define common patterns such as "All mail goes to the Inbox and is
tagged as new, except this mailing list and that junk mail".  Run the
`filter` command on its own to get a brief summary of how to remove,
edit or reorder the filters.


## Protecting your privacy ##

Mailpile doesn't yet know how to read and index encrypted e-mail, but it
will in the future.  In the future Mailpile may also know how to log on to
your remote IMAP and POP3 accounts and download or index remote mail.
This means for sensitive messages, the search index becomes a potential
security risk, as does the configuration file.  More broadly, easy access
to all your communications can be a privacy risk in and of itself:
consider the search `naked att:jpg` as an example.  It is almost certainly
worth taking steps to protect your Mailpile.

One effective strategy, is to store your `.mailpile` folder on an encrypted
volume.

Alternately, if you have a GPG key and run Mailpile in an environment
where gpg-agent is available for key management, you can tell Mailpile to
encrypt its config and data using your key, like so:

    $ ./mailpile.py -S gpg_recipient=youremail@yourdomain.com

**Note:** Currently this only encrypts the main index and config file, and
only works if `gpg` is in your path. The search terms themselves are not
encrypted yet. Like all the others, this feature is a work in progress. :-)


## A word on performance ##

Searching is all about disk seeks.

Mailpile tries to keep seeks to a minimum: any single-keyword search can
be answered by opening and parsing one relatively small file, which should
take on the order of 200-400ms, depending on your filesystem and hard
drive.  Repeated searches or searches for closely related keywords will be
up to 10x faster, due to help from the OS cache.

This *includes* the time it takes to render the list of results.

This level of performance is possible, because all the metadata about the
messages themselves is kept in RAM.  This may seem extravagant, but on
modern computers you can actually handle massive amounts of e-mail this way.

Mailpile stores in RAM about 180 bytes of metadata per message (actual size
depends largely on the size of various headers), but Python overhead brings
that to about 250B.  This means handling a million messages should consume
about 250MB of RAM - not too bad if you consider how much memory your
browser (or desktop e-mail client) eats up.  Also, who has a million
e-mails? :-)

(Caveat: Really common terms will take longer due to the size of the result
set - but searching for really common terms won't give good results anyway.)


## TODO ##

A random laundry list of things I haven't done yet and might accept
patches for:

   * A way to view/extract messages/attachments
   * The ability to compose and send e-mail, and replies
   * Delivery mode for adding a single message to the index
   * Improve conversation IDs assignment
   * Support for other mailbox formats, maybe even POP3/IMAP indexing
   * A shell scripting interface for automation
   * An XML-RPC interface to the search engine
   * A pretty UI on top of said XML-RPC interface

I am especially interested in help with UI work, I suck at that.

Note that Mailpile's emphasis is on *speed* and most of the features
above have already basic designs "in my head".  Chat with me on freenode
(I am BjarniRunar, and hang out on #mailpile) if you're interested in
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

We are roughly at milestone 2, with work beginning on 3.


## Credits and License ##

Bjarni R. Einarsson (<http://bre.klaki.net/>) created this!  If you think
it's neat, you should also check out PageKite: <https://pagekite.net/>

The GMail guys get mad props for creating the best webmail service out
there.  Wishing the Free Software world had something like it is what
inspired me to start working on this.

Contributors:

   * Bjarni R. Einasson (<http://bre.klaki.net/>)
   * Smari McCarthy (<http://www.smarimccarthy.com/>)

This program is free software: you can redistribute it and/or modify it
under the terms of the  GNU  Affero General Public License as published
by the Free Software Foundation, either version 3 of the License, or (at
your option) any later version.

