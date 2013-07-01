# A pile of ideas

These are random ideas that may or may not make sense.  Most of them
were in one way or another inspired by conversations at FSCONS 2011/2012.


## Web interface URL design

Designing the URL space for the web UI is important.  Some ideas:

### Tags:

    http://mailpile/Inbox/
    http://mailpile/Lists/Partalistinn/
    http://mailpile/Lists/Partalistinn/feed.xml
    http://mailpile/Lists/Partalistinn/feed.rss
    http://mailpile/Lists/Partalistinn/feed.json

### Messages:

    http://mailpile/=IDX/messageidsha1sum/
    http://mailpile/=IDX/messageidsha1sum/edit.html
    http://mailpile/=IDX/messageidsha1sum/message.xml
    http://mailpile/=IDX/messageidsha1sum/message.rss
    http://mailpile/=IDX/messageidsha1sum/message.json
    http://mailpile/=IDX/messageidsha1sum/cid:ATTID
    http://mailpile/=IDX/messageidsha1sum/att:COUNT
    http://mailpile/=IDX/messageidsha1sum/inline/4/attachment.jpg
    http://mailpile/=IDX/messageidsha1sum/preview/3/attachment.jpg
    http://mailpile/=IDX/messageidsha1sum/download/3/attachment.jpg

### Searches:

    http://mailpile/?q=search%20terms
    http://mailpile/feed.xml?q=search%20terms
    http://mailpile/feed.rss?q=search%20terms
    http://mailpile/Inbox/?q=search%20terms
    http://mailpile/Inbox/feed.json?q=search%20terms

### Contacts:

    http://mailpile/_/contact/bre@klaki.net/
    http://mailpile/_/contact/contactid/
    http://mailpile/_/contact/contactid.json
    http://mailpile/_/contact/list/bre/
    http://mailpile/_/contact/list/bre.json
    http://mailpile/_/contact/list/--full/bre.json

### Other commands:

    http://mailpile/...?cmd=command%20args
    http://mailpile/_/command?args=args
    http://mailpile/_/command.xml?args=args
    http://mailpile/_/command.json?args=args

### Static content, skins, images, icons, fonts etc.

    http://mailpile/_/static/...


## Power user features

   * Fast for large amounts of e-mail
   * Powerful searching
   * Powerful filters
  --
   * Sticky search: checked messages stay in the list
   * GPG encryption: mail and/or local data
   * GPG indexing: automatic or manual
   * Reply all, reply many, forwarding, bouncing
   * Multiple personalities for composing: name/email/gpg/sig/template
   * Personal mailing lists: if UI is public, allow direct unsubscribe
   * Schedule messages for sending later
   * Built-in web-bug support to know who has read what and when
   * Revokable mail: send an URL, display message in browser.
   * Multimedia composing
   * Collaborative composing
   * Google Translate integration
   * Ability to drop messages from the search index?
   * Facebook integration for photos?
   * Jabber transport to snag for Facebook messages?
   * Markdown!


## Encrypting the index

How much performance to we lose if we GPG encrypt the index?  This would
hurt the indexing process but maybe not general use...

How about the posting lists?  That's gonna hurt all the time.


## GPG integration

Need to be able to index encrypted mail, but it would be ideal if it
weren't trivial to reconstruct encrypted mails using the search index.

Idea: encrypted messages are indexed using random IDs, the random ID
to message-ID mapping is stored encrypted?  What happens if all the
mail is encrypted?

Idea: encrypt the posting lists.  Maybe just the ones referencing
encrypted messages?  Leaky.

Idea: fuck it, just require people encrypt their disks.


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


## Fighting spam

Training a Bayes filter would ideally be done automatically:

   - Replying to a message can be treated as a relatively strong
     indicator that a message is not spam - could lead to
     auto-whitelisting of the sender.

   - Archiving a message or tagging is a weak indicator that a message
     is not spam.

   - Flagging as spam trains the spam filter.

Do we want to implement the mailer fingerprinter?

PageKite allows us to use the web:

   - Folks could submit e-mail using web forms instead of SMTP, where
     anti-comment-spam tech can be used to avoid spam.

   - Borderline spam could potentially get auto-replies directing
     senders to an annoying "prove you are human" form.

Combining Mailpile and PageKite, means mail clients can start talking
to each-other.  Could this be useful for fighting spam?

   - Marking mail AS SPAM or as NOT SPAM could be shared anonymously
     with peers, via. hashes.

   - Reputation information could be shared as well.  But with friends
     only, as it will inevitably leak who you are communicating with?
     The benefit is a potential friends-of-friends whitelist for preventing
     false-positives and allowing spam filters to be more aggressive.


## Packaging ##

Take a look at sickbeard, sabnzbd, couchpotato for inspiration regarding
packaging.

