# README

In this README, we explain how to build and package Mailpile for macOS.
We also provide an overview of the files involved in the packaging process. 

## Packaging Scripts for macOS
The directory containing this README, contains packaging scripts and their required resource files.

### Directory Contents
The following lists the files contained within this directory. The packaging scripts, which build and package Mailpile, are marked in bold.

| File | Description |
| ---- | ----------- |
| appdmg.json.template			| An [appdmg](https://www.npmjs.com/package/appdmg) specification. (Used by package.sh) |
| background/background.png 	| A [.dmg](https://en.wikipedia.org/wiki/Apple_Disk_Image) background image for non-retina displays. (Used by package.sh.)|
| background/background@2x.png| A .dmg background image for retina displays. (Used by package.sh.)|
| **build.sh** 						| A script which builds Mailpile.app. |
| configurator.sh 				| A script which is used by the built Mailpile.app, at runtime. It configures Mailpile.app's GUI. (Used by build.sh.)|
| mailpile 						| A script which is used by the built Mailpile.app, at runtime. It sets environment variables and launches Mailpile. |
| **package.sh** 				| A script which packages Mailpile.app (Mailpile.app is built by build.sh) into a signed .dmg file.|
| README.md 						| This file. |

## Usage
In this section, we state requirements on the build machine, then we demonstrate how to use the packaging scripts.

### Prerequisites
The following software must be installed prior to running the packaging scripts.

- macOS 10.13 (or later) - Available in the App Store.
- Xcode 9.3 (or later) - Available in the App Store.
- Command Line Tools for Xcode - Install them by executing `xcode-select --install` in Terminal.app.
- JDK 10 (or later) - Available on [Oracle's website](http://www.oracle.com/technetwork/java/javase/downloads/index.html).
- Node.js - Available on [nodejs.org](https://nodejs.org/en/). (Provides the following dependency, namely appdmg.)
- appdmg - Install it by executing `npm install -g appdmg` in Terminal.app. (Make sure to add it's install target to *PATH*.)

### Requirements
An internet connection is required as the packaging scripts use [Homebrew](https://brew.sh) and git to fetch dependencies.

You must have installed your [Developer ID certificates](https://help.apple.com/xcode/mac/current/#/dev520c0324f) (both a *Developer ID Application* certificate and a *Developer ID Installer* certificate) into *Keychain Access.app*. See [developer.apple.com](https://developer.apple.com/support/certificates/) to learn how to obtain and install such certificates.

### Environment
Before executing the package scripts, ensure that the following statements are true:

- The directory in which appdmg was installed, is on *PATH*
- You have set the `DMG_SIGNING_IDENTITY` environment variable to be the *ID* of your Developer Certificate. (The ID is the parenthesised part of the certificate's Common Name). This is needed because appdmg does not automatically select a signing certificate. Example: For a certificate which has the Common Name *Mac Developer: Petur Ingi Egilsson (4P78A94863)*, execute `export DMG_SIGNING_IDENTITY=4P78A94863` before launching the build scripts.
- The directory ~/build is empty or non-existing.


### Packaging Mailpile
Packaging Mailpile is a three step process.

1. Execute `export DMG_SIGNING_IDENTITY=4P78A94863` after replacing 4P78A94863 with your Developer Certificate's ID.
2. Execute `./build.sh` in the directory which contains build.sh. This outputs ~/build/Mailpile.app
3. Execute `./package.sh` in the directory which contains package.sh. This outputs ~/build/Mailpile.dmg.

You might want to run ~/build/Mailpile.app to test the build before shipping ~/build/Mailpile.dmg.


## Taxonomy
| Term | Definition |
| ---- | ---------- |
| Mailpile | [Mailpile](https://github.com/mailpile/Mailpile) is a free & open modern, fast email client with user-friendly encryption and privacy features |
| Mailpile.app | A macOS App ([Application Bundle](https://developer.apple.com/library/content/documentation/CoreFoundation/Conceptual/CFBundles/BundleTypes/BundleTypes.html)) which contains Mailpile and it's dependencies. The app also contains a macOS desktop GUI for Mailpile - the GUI which is displayed at launch.
