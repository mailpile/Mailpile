# Welcome to Mailpile! #

[![Build Status](https://secure.travis-ci.org/pagekite/Mailpile.png?branch=master)](http://travis-ci.org/pagekite/Mailpile)

> **NOTE:** This is pre-ALPHA quality code! Please expect everything to
> be broken.

#### Who's doing what? ####

- 2013-11-20: bre: Nose tests, social graph and contact searching
- 2013-11-20: smari: Travis CI and documentation
- 2013-11-18: bnvk: Tweaking the compose UI

#### Recent changes ####

- 2013-11-18: Run `setup` and `rescan` to enable GPG and gravatar importers
- 2013-11-08: New API endpoint /search/address for to/cc/bcc autocomplete
- 2013-11-05: CLI hackers: check out `help hacks` and `hacks/pycli`
- 2013-10-29: Tag metadata greatly was enhanced (please run
  `mp --setup` or `setup` in the Mailpile CLI to update your config).
- 2013-10-28: python-gnupginterface is no longer a dependency.
- 2013-10-22: New config format live, may break many things.

---------------------------------------------------------------------------

## Introduction ##

Mailpile (<http://www.mailpile.is/>) is a free-as-in-freedom personal
e-mail searching and indexing tool, largely inspired by Google's popular
proprietary-but-gratis e-mail service.  It wants to eventually become a
fast and flexible back-end for awesome personal mail clients, including
webmail.

**WARNING:**  Mailpile is still experimental and isn't actually very useful
yet.  It'll tell you that you have mail matching a given search and let
you sort it, browse threads and read messages... but the user interface and
message composing/sending functionality is still very immature.  If you just
want a useful tool and aren't interested in hacking on the code, you should
probably check back later or [follow @MailpileTeam on
Twitter](https://twitter.com/MailpileTeam) and watch for updates.


## Requirements ##

Mailpile is developed on a Debian 7 system, running:

- [Python](http://python.org) 2.7
- [python-imaging](http://www.pythonware.com/products/pil/) 1.1.7
- [python-lxml](http://lxml.de/) 2.3.2
- [python-jinja2](http://jinja.pocoo.org/) 2.6

It might work with other versions, most of these packages can be installed
directly using `apt-get install`. :-)

You also need your e-mail to be in a traditional mbox formatted
Unix mailbox, a Maildir or a gmvault backup repository.

### Installing the requirements ###

On Debian, this should work:

    $ sudo apt-get install python-imaging python-jinja2 python-lxml

Alternately (and on other operating systems) you can use Python's PIP
tool to install the required packages:

    $ pip install -r requirements.txt

Note that installing lxml may require certain C header files that are not
necessarily included on your machine. For Debian-based distributions, this can
be fixed by running:

    $ sudo apt-get install libxml2-dev libxslt1-dev

as per [this Stack Overflow answer](http://stackoverflow.com/questions/15759150/src-lxml-etree-defs-h931-fatal-error-libxml-xmlversion-h-no-such-file-or-di).


## Setting up the basic config ##

For best results, the first step is to tell the program your e-mail
address and set up basic tags (`New`, `Inbox`, etc.) and filters so
Mailpile will behave like a normal mail client.  Mailpile can do this
for you, but if you are importing lots of old mail, you may want to
postpone the filter definition until after the import (see below), to
start with a clean slate:

    $ ./mp --setup
    $ ./mp --set "profiles.0.email = yourmail@domain.com"
    $ ./mp --set "profiles.0.name = Your Name"
    ...

If you do not have a local working mail server in `/usr/sbin/sendmail`,
you may also want to configure a default outgoing SMTP server:

    $ ./mp --set "profiles.0.route = smtp://postmaster@mailserver.org:password@smtp.mailserver.org:25"
    ..

Mailpile does not by default access IMAP or POP3 servers directly, it
relies on other tools (such as `fetchmail`) to take care of downloading
new mail.

**Note:** You can add multiple accounts by replacing the `0` in the profile
variable name with higher numbers.


## Indexing your mail ##

Mailpile will create and use a folder in your home directory named
`.mailpile` for its indexes and settings.

A simple test run might look like so:

    $ ./mp --add /var/spool/mail/YOURNAME --rescan all

The program prints details of its progress as it runs.  Note that just
opening the mailbox may take quite a while if it is large enough (it
takes about a bit over a minute to open my 500MB mailbox).  Once the
mailbox has been opened, my laptop (a 1.66Ghz Intel Atom with a 5400rpm
HDD) the program can index roughly four messages per second, so if you
are processing thousands of messages you should expect it to take a few
hours.

You can repeat the add command to specify multiple mailboxes.  Boxes
can be in mailbox or maildir format.  Boxes are not recursive, though.
If you have many maildirs in a tree, you must specify each one
individually.

Stopping the program with CTRL-C is (relatively) nondestructive - it
will try to save its progress and re-running should continue the scan
from where it left off.


## Web interface ##

Mailpile has a built-in web server and will eventually include a proper
web-based interface for searching, reading and composing e-mail.

The web interface currently has just one input field, where you can
type terms to search for.  If you start the line with a `/` character
you can use any of the normal CLI commands, including viewing tags or
reading messages (`/view 1-15`).

Maybe someday you will build a fancier UI for us. :-)

If you want to run the web UI without the CLI interface, start the
program like this:

    $ ./mp --www

The server listens on `localhost:33411` by default, meaning you cannot
access it from a different computer (for security reasons). You can change
the host and port by setting the `http_host` and `http_port` variables
(more about [internal variables](#internal-variables) below).
For example if you want to run the server to be accessible
from another computer as well, you can run Mailpile
with:

    $ ./mp --set sys.http_host=0.0.0.0

Setting `sys.http_host` to `disabled` disables the server.


## Basic use ##

The most important command Mailpile supports is the `search` command.
The second most important is probably `help`. :-)

All commands can be abbreviated to only their first character (the less
commonly used commands use capital letters for this).

### Searching ###

Some searching examples:

    $ ./mp
    mailpile> search bjarni einarsson
    ...
    mailpile> search subject:bjarni
    ...
    mailpile> search from:bjarni to:somebody
    ...
    mailpile> search from:bjarni -from:pagekite
    ...
    mailpile> search group:family -from:mom
    ...
    mailpile> s att:pdf
    ...
    mailpile> s has:attachment
    ...
    mailpile> s date:2011-1-30 +date:2011-1-29
    ...
    mailpile> s year:2011 month:12
    ...
    mailpile> s dates:2011-12..2012-04-15
    ...
    mailpile> s mailbox:path/fragment/or/filename
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

You can also search from the command line with `mp -s term`,
but that will be a bit slower because the metadata index has to be
loaded into RAM on each invocation.


#### Special search terms ####

Here is a brief list of the special search terms:

    all:mail         All messages
    att:<word>       Search within attachment file names
    dates:<B>..<E>   Search dates from B to E
    in:spam          Same as tag:Spam
    in:trash         Same as tag:Trash
    is:unread        Same as tag:New
    group:<name>     Messages from people in a group
    has:attachment   Messages with attachments
    has:pgp          Messages with signed or encrypted content
    togroup:<name>   Messages to people in a group


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

    mailpile> tag add Inbox
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

- `all` will affect all messages
- `these` will affect currently listed messages
- A list of numbers or ranges (`1 2 3 5-10 15`)

All these are relative to the last search, so `1` is the first result
of the most recent search and `all` would be all matching messages.

Tags names are themselves recognized as specialized search commands in
the `mailpile` CLI.

If you want Mailpile to automatically tag (or untag) messages based on
certain search criteria, you can use the `filter` command instead:

    mailpile> tag add Lists/Diaspora
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

The simplest and most effective strategy, is to store your `.mailpile`
folder on an encrypted volume.

Alternately, if you have a GPG key and run Mailpile in an environment
where gpg-agent is available for key management, you can tell Mailpile
to encrypt its config and data using your key, like so:

    $ ./mp --set "prefs.gpg_recipient = youremail@yourdomain.com"

Note that this only encrypts the main index and config file, and only
works if `gpg` is in your path. The search terms themselves are not
encrypted, which means the contents of individual messages could at
least in part be derived from the index.  This problem can be mitigated,
at the cost of some performance, by telling Mailpile to use a one-way
hash to obfuscate the search terms:

    $ ./mp --set "prefs.obfuscate_index = Some RaNdoM LongISH SECRET"

Note that if you change this setting, whatever has already been indexed
will "disappear" and become unfindable.  So do this first if you do it
at all!


## Hacking and exploring ##

### Code structure ###

Mailpile's python code lives in `mailpile/`.

Mailpile's default HTML templates and Javascript lives in `static/default/`

Miscellaneous documentation is in `doc/`.

Test data lives in `testing/`.


### Internal variables ###

There are a bunch of variables that can be tweaked. For a complete list:

    mailpile> help variables
    ...

To set a variable to some value either run Mailpile with:

    $ ./mp --set section.variable=value

Or alternatively run `./mp` and issue:

    mailpile> set section.variable=value

after which you need to restart the program for it to take effect
(Ctrl+D and `./mp`). You can print the value of a variable using:

    mailpile> print variable


### Testing ###

We are slowly migrating the code to use the `doctest` module for
internal unit tests.

Black-box regression tests can be invoked by running
`scripts/mailpile-test.py`.  For experimenting and testing, the blackbox
test script can be run in an interactive mode:

    $ ./scripts/mailpile-test.py -i


### JSON, XML, RSS, ... ###

JSON and XML versions exist for most web-based commands and requests
and most Mailpile functionality is (or will be) accessible over an
HTTP REST-style API.

Please see `doc/URLS.md` for details.


### Developing using virtualenv ###

The `Makefile` includes a recipe for setting up a virtualenv for use
with Mailpile:

    $ make virtualenv
    $ source mp-virtualenv/bin/activate
    $ mailpile

This allows easy, sandboxed usage.


### Developing using docker ###

You can build a docker image:

    $ docker build -t mailpile scripts/docker/

and run it:

    $ docker run -i -t mailpile

or enter the container's bash prompt directly:

    $ docker run -i -t mailpile bash

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


## Credits and License ##

Bjarni R. Einarsson (<http://bre.klaki.net/>) created this!  If you think
it's neat, you should also check out PageKite: <https://pagekite.net/>

The GMail guys get mad props for creating the best webmail service out
there.  Wishing the Free Software world had something like it is what
inspired me to start working on this.

Contributors:

- Bjarni R. Einasson (<http://bre.klaki.net/>)
- Smari McCarthy (<http://www.smarimccarthy.is/>)
- Brennan Novak (<https://brennannovak.com/>)
- Lots more, run `git log |grep Author |sort |uniq -c` for a list!

This program is free software: you can redistribute it and/or modify it under
the terms of either the GNU Affero General Public License as published by the
Free Software Foundation or the Apache License 2.0 as published by the Apache
Software Foundation. See the file `COPYING.md` for details.

