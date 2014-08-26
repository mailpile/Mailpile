## Mailpile Packaging for Mac OS X

This folder contains tools pertaining to the Mac OS X bundling of
Mailpile.


### Repackaging on Linux

If you are on Linux and just want to repackage the latest Mailpile HEAD
as a DMG, there is a `repackage-linux.sh` script which does all the
interesting stuff and leaves a .dmg file in `/tmp/mailpile-builder/`.


### How it works

The current method for packaging Mailpile is as follows:

   1. Use Homebrew and some shell magic to build a folder containing all
      our dependencies.  The script `brew-package.sh` captures the logic
      behind this, but whether it runs depends on the current state of
      the Homebrew github master.  If it's not working for you, a working
      tree can be downloaded from:
      <https://www.mailpile.is/files/build/Mailpile-Brew.LATEST.tar.gz>

   2. Use Platypus to build a basic app tree for Mailpile, invoking the
      `mp-in-terminal.sh` script found in this folder.  The results of
      this process can be found in `Mailpile.app-platypus.tgz`.

   3. For development, symlink in your Mailpile git repo as `Mailpile`
      in `Mailpile.app/Contents/Resources`.  Symlink in, or copy the
      `Mailpile-Brew` folder to the same location.

   4. For distribution, do the same as 3. except use real copies, not
      symbolic links.

   5. To package all this up, we create a .dmg containing the Mailpile.app,
      a symbolic link to /Applications/ and configure the folder background
      with `welcome-to-mailpile-bg1.png`.  Then use the Disk Tool to convert
      that .dmg to a compressed read-only volume.

That's about it!


### Notes:

   * Sometimes the Mac Finder is dumb about symbolic links, which can
     bloat up the size of the resulting app.  I like to use `tar` to
     copy things around instead, it does the right thing

