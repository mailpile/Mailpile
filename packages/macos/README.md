# README

This directory contains:
* build.sh - A build scripts which outputs ~/build/Mailpile.app
* configurator.sh - A script which is copied into Mailpile.app. GUI-o-Mac-tic uses it as a GUI-configuration data source, the script is called just after Mailpile.app is launched but before the GUI is shown.
* mailpile - A wrapper around mailpile which sets up the environment in which Mailpile is to run.

## Usage
Execute build.sh.

## Known Limitations
* The resulting Mailpile.app is 353 MiB. It contains files which are not needed and can safely be deleted. A list of those files is yet to be compiled.
* On some systems, the user can not log on Mailpile after the initial setup because Mailpile claims the user has entered a wrong password.
