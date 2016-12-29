## Mailpile Developer FAQ

This document contain a collection of frequently asked questions (with
answers) about Mailpile development. Please familiarize yourself with
the contents before attempting to hack on Mailpile.

You don't have to agree with all of our priorities to take part or make
use of Mailpile, but we do feel it helps if most of the community is
rowing in roughly the same general direction!


#### Why Mailpile?

The long-term goal of Mailpile is to help *non-technical people* become
**more independent** and **more private** online, online, in particular
when it comes to e-mail.

By **more independent**, we mean users should be in control of their
e-mail and the software used to manage it. This is why Mailpile is Free
Software, and this is why we *don't* promote Mailpile as a tool for
building "cloud services".

By **more private**, we mean users should have more control over who has
access to their e-mail, when and how. This is why Mailpile tries to make
e-mail encryption more accessible, and this is why Mailpile tries to
make it convenient *and secure* for users to store their e-mail on their
own devices.

Our focus on *non-technical users* implies, amongst other things, that
we cannot exclude people who are using non-free platforms such as
Microsoft Windows or Mac OS X, and we cannot require our users learn a
radically new, unfamiliar user interface or understand highly technical
concepts such as public key cryptography.


#### Are All of These Decisions Awesome?

No. Some of these decisions were almost certainly mistakes. But that's
part of innovating, you try new things and see how they go!

So we kindly request that our contributors and collaboratores refrain
from picking arguments with us over these decisions. Making forward
progress is much more fun than rehashing the past over and over again.


#### Why Do You Reinvent So Many Wheels?

Usually, the answer is one or more of the following:

   * We didn't know a solution already existed
   * We evaluated solutions X, Y and Z, but didn't like them
   * We felt the problem was simple enough to Just Do It

In general, we are reluctant to take on new external dependencies unless
they are stable and widely available: if they exist in pre-packaged form
for Windows, Mac OS X and the most common Linux distributions, they are
probably fine!

If not, the benefits need to outweigh the added complexity posed for our
cross-platform packaging efforts.

For this reason we also tend to prefer pure-Python (or Javascript, for
the UI) libraries over native code, which also avoids certain classes of
security holes which are simply not present in a memory-safe, managed
language.

We have broken this rule more often than we'd like in our user-interface
code, due to cultural differences between web developers and Python
folks. *We would like to gradually reduce our front-end dependencies.*


#### Why a Search Engine?

Mailpile started as an experimental search engine, a hobby project.
Everything else came later.

*OK, so why not replace it with a standard component?*

Because it works! Replacing it at this point would be *more work, not less*.

Also, we are unaware of any "off the shelf" search engines that let us
encrypt their data stores and we feel encrypting the search index is an
absolute requirement since we by default allow the user to search inside
encrypted messages.

*I see. Why not remove it, to simplify the code?*

The entire app is built around the search metaphor, much like Google's
GMail. This is a fundamentally different way to build an e-mail client,
from the traditional "messages and mailboxes" model.

The search engine also makes it easy for Mailpile to do some very
interesting things internally; some examples:

   * we can evaluate the trustworthiness of a message by asking the
     search engine about the past behaviour of the sender
   * we can postpone processing of things like attached PGP keys until
     we actually intend to use the key: the search engine makes the keys
     easy to find later on


#### Why doesn't Mailpile have a Native User Interface?

For now, because the team is very small and we would like to reach users
on many different platforms, we have bet entirely on the web as our
primary user interface.

This decision allows us to target any operating system for which Python
2.7 has been made available.

It also allows us to get help from the enormous community of web
developers; this is a much larger talent pool than the pool of
developers that know how to write native apps.

Last but not least, the web interface is key to our plan to allow users
to access their Mailpile remotely over the network. Remote access is
critical if we want to get people to store their e-mail on their own
devices, since most people read their mail on multiple devices (laptop,
tablet, mobile, work computer, etc).

That said: we do want to have a minimal native user interface, on all
the major desktop operating systems. [That is what the gui-o-matic
spin-off project is about](https://github.com/mailpile/gui-o-matic).

Native mobile apps on Android and/or iOS would also be nice to have!


#### What is Mailpile's Approach to Security?

This is a huge topic! Please consult our [Security
Roadmap](https://github.com/mailpile/Mailpile/wiki/Security-roadmap).

Security is complex and means different things to different people.

The most controversial questions relating to security, have to do with
mass surveillance and law enforcement. Mailpile's stance is that we
believe that people have an innate right to privacy we believe that mass
surveillance is *wrong*. If the government wants to read your e-mail,
we feel they should present you with a search warrant.

Thwarting other adversaries (criminals, jealous partners, etc.) is also
very much something we care about, but is probably less divisive.


#### Why GnuPG? Why not GPGME? Why not PGPy?

GnuPG is mature, stable and although the user interfaces may leave
something to be desired, it has a rich ecosystem of powerful tools built
around it. If we didn't use GnuPG, we would have to reinvent a lot of
wheels that aren't central to Mailpile's mission. Our issue tracker
contains [further discussions on the topic of why GnuPG and not something
else, such as PGPy](https://github.com/mailpile/Mailpile/issues/1743).

[Use of GPGME is also being
discussed](https://github.com/mailpile/Mailpile/issues/1742). Currently,
we don't feel GPGME provides enough benefit to justify the additional
dependency and the additional (hypothetical) risk posed by solving the
GnuPG integration problem with a large amount of code written in C (as
opposed to Python, which is memory-safe and less likely to contain
certain classes of security vulnerabilities).


#### Why Not Django? Or Flask?

Reasons!

The text-based command-line interface is an important part of Mailpile's
user interface. Our home-brewed framework allows us to generate web API
end-points, text commands and command-line arguments *at the same time*.

Our internal framework also has the concept of commands supporting
multiple output formats; so the same API endpoint can generate text,
templated HTML, JSON and XML-RPC interfaces with relatively little
additional code. Some endpoints also generate XML, CSV, CSS or
Javascript.

You can try this yourself, simply by editing the URL in your browser:

    # The default, rendered as HTML
    http://localhost:33411/in/inbox/
    http://localhost:33411/in/inbox/as.html
    http://localhost:33411/search/?q=in:inbox

    # Same thing, as JSON
    http://localhost:33411/in/inbox/as.json
    http://localhost:33411/api/0/search/?q=in:inbox

    # Same thing, as text
    http://localhost:33411/in/inbox/as.text
    http://localhost:33411/api/0/search/as.text?q=in:inbox

The filename part of the URL is used to select output formats. All
endpoints support `as.json`, most support HTML and/or text.

Our way may be unsual, but it's kinda awesome once you get used to it
and it wasn't obvious to us how we could get this kind of behaviour from
one of the standard frameworks.


### Why not Python 3?

We depend on some libraries - spambayes in particular - which were not
available for Python 3 when we started this project.

We don't think Python 2 is going away in the near future.

[There is a Github issue discussing
this.](https://github.com/mailpile/Mailpile/issues/160)
