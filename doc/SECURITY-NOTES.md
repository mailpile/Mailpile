# Misc Security Notes #

## Updates

Use the UW protocol? Bittorrent prevents us from targeting
individual users!


## Securing Workflows

It can be important to make sure workflows can only be done in
the order specified. This can be done by passing variables that
link step1 to step2 so skipping step1 (or tricking someone into
skipping step1) is impossible.


## Watch out for interacting with the filesystem

Comparisons with strings in Python may differ with those in the
OS/FS layer, especially due to Unicode complicating everything.

Treating paths as byte-lists and strictly limiting which chars
are allowed (kill the unicode) can help.


## Unicode scaryness

An entire class of bugs can be eliminated if data is dumbed down
to ASCII as soon as it enters the system. This may be OK for things
like the URL path, impossible for input variable values.


## Faking type-strictness in Python (taint checking)

Wrapper classes that have funny instance variables or getters
which signify "untainted" data.  Passing a string directly or
some other data which has not been "cleaned" will trigger an
AttributeError exception.


## Libraries

This library is an anti-XSS library. Check it? 
http://code.google.com/p/reform/

OWASP anti-samy, helps make HTML safe to display.


# Viruses

Statement of intent?  How do we deal with them?  Format verification,
include ClamAV?  Recommended way would be to neutralize content into
known-safe forms by converting images to themselves, PDF rendered in
JS, etc.


# PGP etc.

## Downloading keys by default?

Should probably be done by default unless a message signals somehow
that it is meant to be anonymous.

If we have a p2p channel, requesting keys over that could make sense
for a TOFU model.

## Regarding web of trust

Ella recommends against using it, because the WoT generates a
persistent and public social graph that can be mined by adversaries.
Along with a historic record.

Also it does not work.

## Keys and trust

Things to tell the user:

   * You have not seen this key before, and have not verified it.
   * You have seen this key before, but have not verified it.
   * You have seen this key before, and have verified it.
   * This key is different from what that person presented last time.
       * Is new key signed by old key? (OK, shutup)
       * The old key was about to expire
       * The old key was revoked
       * This might be weird.

## Key generation

Should be automatic, using best practices, 4K RSA, expiration?
2-3 years?

Questions to a minimum: Do you have a key? Upload to keyserver?

On expiration, Mailpile could automatically generate new keys
and sign with old keys and upload. Depending on pres.

Life-stylers vs. normal humans, punt to the command-line for
people who do not like the Mailpile GPG model. Or if possible
make it a "build your own plugin" problem.


## Anonymity

Support Tor for connecting to IMAP/SMTP.

Mixmaster/mixminion (later): We know the NSA can probably do
timing analysis on Tor. Mix networks, if they had traffic and
were maintained, would resist this. Clearsigned e-mails
exiting from mix nodes could provide cover traffic. Ask users
"do you wanna help make the network anonymous?". Delays
things... button to "send fast"? ..... Ella says: IMPORTANT.
Consider this as an alternate transport.


## The SSL nightmare

Optimal case:

   1. Help people buy domains
   2. Buy keys
   3. Make end-to-end TLS over pagekite easy

Make sure SPF gets configured, think about DKIM.

Others: self-signed, pagekite MITM.


