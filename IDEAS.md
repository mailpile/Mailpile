# A pile of ideas

These are random ideas that may or may not make sense.  Most of them
were in one way or another inspired by conversations at FSCONS 2011.


## Encrypting the index

How much performance to we lose if we GPG encrypt the index?  This could
hurt the indexing process but maybe not general use...


## Tahoe-LAFS integration

Once a significant amount of e-mail has been indexed, tagged and sorted,
losing the index becomes a serious problem.

Backing up is the obvious solution (and not necessarily Mailpile's problem),
but it would be interesting to explore the option of integrating with
Tahoe-LAFS to provide "out of the box" secure distributed storage.


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


