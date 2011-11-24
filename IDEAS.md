# A pile of ideas

These are random ideas that may or may not make sense.  Most of them
were in one way or another inspired by conversations at FSCONS 2011.


## Web interface URL design

Designing the URL space for the web UI is important.  Some ideas:

### Tags:

    http://mailpile/Inbox/
    http://mailpile/Lists/Partalistinn/
    http://mailpile/Lists/Partalistinn/feed.xml
    http://mailpile/Lists/Partalistinn/feed.json

### Messages:

    http://mailpile/=IDX/messageidsha1sum/
    http://mailpile/=IDX/messageidsha1sum/message.xml
    http://mailpile/=IDX/messageidsha1sum/message.json
    http://mailpile/=IDX/messageidsha1sum/thread.json
    http://mailpile/=IDX/messageidsha1sum/thread.xml
    http://mailpile/=IDX/messageidsha1sum/inline/4/attachment.jpg
    http://mailpile/=IDX/messageidsha1sum/preview/3/attachment.jpg
    http://mailpile/=IDX/messageidsha1sum/download/3/attachment.jpg

### Searches:

    http://mailpile/?q=search%20terms
    http://mailpile/feed.xml?q=search%20terms
    http://mailpile/Inbox/?q=search%20terms
    http://mailpile/Inbox/feed.json?q=search%20terms

### Other commands:

    http://mailpile/...?cmd=command%20args
    http://mailpile/_/command?args=args
    http://mailpile/_/command.xml?args=args
    http://mailpile/_/command.json?args=args


## Encrypting the index

How much performance to we lose if we GPG encrypt the index?  This would
hurt the indexing process but maybe not general use...


## Tahoe-LAFS integration

Once a significant amount of e-mail has been indexed, tagged and sorted,
losing the index becomes a serious problem.

Backing up is the obvious solution (and not necessarily Mailpile's problem),
but it would be interesting to explore the option of integrating with
Tahoe-LAFS to provide "out of the box" secure distributed storage.

... but it would probably be too slow.  An alternative, now that mailpile
knows how to GPG encrypt/decrypt things, is to add unhosted support or
webdav.  That might get us Tahoe-LAFS for free anyway?


## Remote sources and sync

Mailpile currently recognizes duplicate messages by Message-ID, and assumes
that discovering a duplicate within the same mailbox means the message has
been edited/moved.

It silently ignores duplicates found in other mailboxes, which is probably
not great behavior, instead it should probably track all locations for a
message (update: this has been fixed).

This in turn implies a backup/sync option: Mailpile could enforce a policy
of all messages always existing in multiple mailboxes OR a simpler policy
where one mailbox always mirrors the others.

This in turn leads to questions about versioning, which is a big topic...


## Collaboration and access controls

If tags are given an "access control" characteristic, Mailpile's web
interface could be useful for:

   * Collaboration on mail
   * Support / Forums
   * Instant mailing list archives
   * Blogging and comments


## RSS integration

Reading mail and reading RSS are really similar.  Indexing RSS feeds
would be kinda awesome.

However - once we start indexing other peoples' content we quickly end
up with an order of magnitude more data and the index-in-RAM strategy
may become untenable.  It's like busy mailing lists, only worse.


## Searching other things

It's a search engine.  It could search the web, but more realistically
it might be useful as a super-bookmarking tool which indexes arbitrary
pages on demand.  We'd want a mirroring feature to go with this though.


