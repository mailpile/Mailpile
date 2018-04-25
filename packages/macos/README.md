# README

This directory contains:
* build.sh - A build scripts which outputs ~/build/Mailpile.app
* package.sh - A package scripts which places ~/build/Mailpile.app into a signed DMG file.
* configurator.sh - A script which is copied into Mailpile.app. GUI-o-Mac-tic uses it as a GUI-configuration data source, the script is called just after Mailpile.app is launched but before the GUI is shown.
* mailpile - A wrapper around mailpile which sets up the environment in which Mailpile is to run.
* appdmg.json.template - A template used by appdmg when building a .dmg.
* background.png - The background to be used in the .dmg file built by package.sh.
* mailpile.icns - The icons to be used in the .dmg file built by package.sh.
* background/background.png - The background used in the .dmg when mounted on a non-retina display.
* background/background@2x.png The background used in the .dmg when mounted on a retina display.


## Dependencies
* Java Platform (JDK) (http://www.oracle.com/technetwork/java/javase/downloads/)
* appdmg (A node package, see: https://github.com/LinusU/node-appdmg)
* Xcode (Available in the App Store)
* Xcode Command Line Tools (On a clean install, type 'git' in Terminal.app and macOS will offer you to install the Xcode tools).

## Usage
### Creating Mailpile.app
Execute build.sh.

### Creating Mailpile.dmg
Set the environment variable DMG_SIGNING_IDENTITY to hold the ID of Mac Developer certificate which is to be used when signing the .dmg. The certificate's ID is the string shown within parenthesis in the Keychain Access.app.
Execute package.sh.

## Known Limitations
* The resulting Mailpile.app is 353 MiB. It contains files which are not needed and can safely be deleted. A list of those files is yet to be compiled.
* On some systems, the user can not log on Mailpile after the initial setup because Mailpile claims the user has entered a wrong password.
