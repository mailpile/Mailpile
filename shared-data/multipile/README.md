## Multipile: multi-user Mailpile

Here you can find tools to simplify administration of a smallish multi-user
Mailpile installation.


### Requirements and Prerequisites

   * Mailpile, Apache 2+, sudo and screen
   * Each user who wants to use Mailpile, exists as a Unix user
   * You *really* should configure your server to use TLS-encryption!


### How does it work?

Once configured, `https://your-server/mailpile/` should present you with a
log-in page.

Apache is configured to proxy incoming traffic to/from running Mailpile
processes, mapping usernames to localhost port numbers. If a user's Mailpile is
not running, the user is presented with a log-in page that requests a username,
which is in turn passed to `mailpile-admin.py` (running as a CGI) which
launches a much simpler (=secure?) script named `mailpile-launcher.py` via
`sudo`.

The launcher will attempt to launch the user's Mailpile in a background screen
session owned by that user. The launcher will only launch Mailpiles for users
that have used the app at least once in the past (their Mailpile data directory
must exist). The recommended way to configure new users is using the
`mailpile-admin.py` tool as described below.


### Using mailpile-admin.py

The tool `mailpile-admin.py` does most of the heavy lifting.

The admin can use this tool manually to list, add, remove and otherwise manage
Mailpile installations:

    ## Enable and start Mailpile for the user frank
    $ sudo ./mailpile-admin.py --user frank --start
    ...

    ## Stop the running Mailpile for bob
    $ sudo ./mailpile-admin.py --user bob --stop
    ...

    ## Delete all a user's Mailpile data! Requires adding the --force argument.
    $ sudo ./mailpile-admin.py --user bob --delete

    ## List running or configured Mailpile instances
    $ sudo ./mailpile-admin.py --list
    ...
    

The tool can also be used to (try to) automatically configure Apache2 to serve
Mailpile on the `/mailpile/` path of the default VHost.

    ## Configure Apache for use with multi-user Mailpile
    $ sudo ./mailpile-admin.py --configure-apache
    
If you have installed the `mailpile-apache2` Debian package, this will already have
been done for you.


### Mini-FAQ

Q. Where can I find the `mailpile-admin.py` tool? It's not on my path?  
A. The Debian package installs Multipile in `/usr/share/mailpile/multipile`

Q. Why doesn't my Mailpile start up when I enter my username?  
A. Your admin probably needs to run: `mailpile-admin.py --start --user YOU`

Q. Why not nginx or some other better web-server?  
A. Nobody has contributed the necessary recipies yet! Please do!

Q. I had already run Mailpile manually, how to I migrate to Multipile?

   1. Install Multipile: `apt install mailpile-apache2`
   2. Launch your personal Mailpile, leave it running
   3. Run `sudo mailpile-admin.py --list`, your Mailpile *should* be listed
   4. If so, run `sudo mailpile-admin.py --discover --configure-apache-usermap`
   5. In your Mailpile CLI, run `www http://127.0.0.1:PORT/mailpile/USER/`,
      with PORT and USER matching the values shown in step 2 above. Careful, the
      trailing slash IS important.

Q. Can't I just edit the usermap (rewritemap) by hand?  
A. Sure! It should be here: `/var/lib/mailpile/apache/usermap.txt`

