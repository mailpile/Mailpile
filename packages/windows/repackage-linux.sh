# This script makes a Mailpile Windows installer from the Mailpile source code,
# Python distribution files and other source code, which are all downloaded from
# the "official" Internet site of each software provider. 
#
# This has been tested on Debian Stretch.
# Required Debian packages (this list may be incomplete):
# git gnupg gzip mingw-w64 nsis openssl p7zip python2.7 python-pip tar unzip
# wget xz-utils (? archiver used by GnuPG build?)   
# 
# Copyright (C) 2017,2018 Jack Dodds
# This script is part of Mailpile and is hereby released under the
# Gnu Affero Public Licence v.3 - see ../../COPYING and ../../AGPLv3.txt.

# Uncomment to hard code a version identifier.
# VERSION="1.0.0rc2"

# Configuration strings:
# (Do not use embedded spaces or environment variables.)

MAILPILE_GIT="https://github.com/mailpile/Mailpile.git"
MAILPILE_BRANCH=master

PYTHON_SITE="https://www.python.org/ftp/python/2.7.15/"
PYTHON_FILE="python-2.7.15.msi" 
# Checksum from https://www.python.org/downloads/release/python-2715  No SHA256!
PYTHON_FILE_MD5=023e49c9fba54914ebc05c4662a93ffe
REQUIREMENTS="requirements-with-deps.txt"

MPLAUNCHER_SITE="https://www.mailpile.is/files/build/"
MPLAUNCHER_FILE="MailpileLauncher.zip"
MPLAUNCHER_FILE_SHA256=\
fad7ee1a4a26943af8f20c7facc166c34f84326c02ee0561757219bbd330e437

OPENSSL_SITE="https://www.openssl.org/source"
OPENSSL_FILE="openssl-1.1.0h.tar.gz"
# Checksum from https://www.openssl.org/source/openssl-1.1.0h.tar.gz.sha256
OPENSSL_FILE_SHA256=\
5835626cde9e99656585fc7aaa2302a73a7e1340bf8c14fd635a62c66802a517

GNUPG_SITE="https://www.gnupg.org/ftp/gcrypt/gnupg"
GNUPG_FILE="gnupg-2.2.7.tar.bz2"
# Checksum from https://lists.gnupg.org/pipermail/gnupg-announce. No SHA-256??
GNUPG_FILE_SHA1=e222cda63409a86992369df8976f6c7511e10ea0
# Pattern for archive generated in build process including 3rd party source.
GNUPG_FILE_ALL="gnupg-w32-2.2.7_*.tar.xz"

# End of configuration strings.

# Capture path to package script directory, go there.
set -e
cd "$(dirname "$0")"
SCRIPTDIR="$(pwd)"

# Command line arguments can be used to change default repository and branch.
for ARG in $* ; do
    if [ $ARG = "--local" ]; then
        MAILPILE_GIT="file://$(realpath $(pwd)/../.. )"
    elif [ $ARG != *- ]; then
        MAILPILE_BRANCH=$1
    else
        echo "Bad command line argument"; exit
    fi
    shift
done

echo " "
echo "Mailpile repository:  $MAILPILE_GIT"
echo "Mailpile branch:      $MAILPILE_BRANCH"

# Get the enclosing project directory path,
# define a path for downloads from external projects like GnuPG and OpenSSL.
PROJECTDIR=$(realpath $SCRIPTDIR/../..)
echo "Project dir:          $PROJECTDIR"
echo "Script dir:           $SCRIPTDIR"
DOWNLOADDIR=$PROJECTDIR/SourceArchive
echo "Source download dir:  $DOWNLOADDIR"
PYTHON_DL=$PROJECTDIR/PythonDistFiles
echo "Python download dir:  $PYTHON_DL"

# Create build directory.
rm -rf /tmp/mailpile-winbuild           # Use rm -rf with hardcoded path only!
WORKDIR="/tmp/mailpile-winbuild"
mkdir $WORKDIR
echo "Working dir:          $WORKDIR"
echo " "
sleep 5

# Get Mailpile.
cd $WORKDIR
git clone --branch $MAILPILE_BRANCH --depth=1 --recursive $MAILPILE_GIT Mailpile
cd Mailpile

# Get commit and version identifier from checked out Mailpile.
iCOMMIT=`git log -1 --pretty=format:"%h"`
if [$VERSION == ""]; then
    export VERSION=`scripts/version.py`
fi

# Create source archive directory and put archive of Mailpile in it.
SOURCEARCHIVEDIR=$WORKDIR/SourceWin$VERSION
mkdir -p $SOURCEARCHIVEDIR
cd ..
tar -c --file $SOURCEARCHIVEDIR/Mailpile-$COMMIT.tar.gz --gzip Mailpile
cd Mailpile

# Create install directories for Python and its packages
# Dummy file ensures archive programs will not ignore.
mkdir -p Python27/Lib/site-packages
echo " " >  Python27/Lib/site-packages/dummy

# Get the distribution files for Python and all needed packages
# Then copy them to the installer image.

echo " "
echo "Get Python"
mkdir -p $PYTHON_DL; cd $PYTHON_DL

if [ -e $PYTHON_FILE ]; then
    echo "    Reusing previously downloaded Python MSI file"
    echo "    To force download, delete $PYTHON_DL/$PYTHON_FILE"
else
    echo "    Download Python MSI file"
    wget -c $PYTHON_SITE/$PYTHON_FILE || true
fi
# Test source code integrity.
if [ `openssl dgst -md5 -hex $PYTHON_FILE | cut -d " " --f 2` != \
    $PYTHON_FILE_MD5 ]
then
    echo "File integrity check failed"
    exit
fi

# Get distribution files for Python packages listed in $REQUIREMENTS.
# First try for a Python 2.7 Win32 .whl file.
# (Python won't install these on a Linux build system, but will download them.)
# If none, try for a pure Python package.
# FIXME: pip downloads latest version even if earlier version is present
# FIXME: Does pip check file integrity?
    echo " "
    echo Get pypiwin32      # Get pypiwin32 even if it is not in $REQUIREMENTS.
    python -m pip download --no-cache-dir --no-deps --dest $PYTHON_DL \
                pypiwin32 \
                --only-binary :all: --platform win32 --python-version 27
while read PACKAGE; do
    # Python MSI file already includes pip and setuptools.
    if [ $PACKAGE == pip* ] || [ $PACKAGE == setuptools* ]; then continue; fi
    
    echo " "
    echo "Get $PACKAGE"
    if ! python -m pip download --no-cache-dir --no-deps \
                --dest $PYTHON_DL $PACKAGE \
                --only-binary :all: --platform win32 --python-version 27
    then
    echo "No binary package - request pure Python package"
        python -m pip download --no-cache-dir --no-deps --dest $PYTHON_DL \
                $PACKAGE --no-binary :all:
    fi
done < "$WORKDIR/Mailpile/$REQUIREMENTS"

cp -r $PYTHON_DL -t $WORKDIR/Mailpile

# Get non-Python packages

# Create subdirectory for downloading 3rd party source code
mkdir -p $DOWNLOADDIR

# MailpileLauncher 
# FIXME: At present this has to be built externally with MS Visual Studio.
# FIXME: File integrity check?

echo " "
echo "Get MailpileLauncher"
if [ -e $SCRIPTDIR/MailpileLauncher/Mailpile.exe ]; then
    echo "    Reusing previously downloaded MailpileLauncher"
    echo "    To force rebuild, delete $SCRIPTDIR/MailpileLauncher"
else
    cd $DOWNLOADDIR
    if [ ! -f $DOWNLOADDIR/$MPLAUNCHER_FILE ]; then    
        echo "    Downloading MailpileLauncher"
        wget -c $MPLAUNCHER_SITE/$MPLAUNCHER_FILE || true
    fi   
    # Test source code integrity.
    if [ `openssl dgst -sha256 -hex $MPLAUNCHER_FILE | cut -d " " --f 2` != \
        $MPLAUNCHER_FILE_SHA256 ]
    then
        echo "File integrity check failed"
        exit
    fi
    cd $SCRIPTDIR
    rm -rf MailpileLauncher/*
    unzip -q $DOWNLOADDIR/MailpileLauncher.zip
    mv -f MailpileLauncher/MailpileLauncher/* MailpileLauncher
    rm -r MailpileLauncher/MailpileLauncher
    
    # FIXME: 2017-11-08 the Mailpile.exe.cfg file from www.mailpile.is is bad.
    cp launcher.exe.config MailpileLauncher/Mailpile.exe.config
fi
cp -r $SCRIPTDIR/MailpileLauncher/* -t $WORKDIR/Mailpile

# OpenSSL
#
# See ./Configure and ./Makefile in OpenSSL source tree for options and targets.
# See https://marc.wäckerlin.ch/computer/cross-compile-openssl-for-windows-on-linux
#
echo " "
echo "Get OpenSSL"
if [ -e $SCRIPTDIR/OpenSSL/bin/openssl.exe ]; then
    echo "    Reusing previously built OpenSSL"
    echo "    To force rebuild, delete $SCRIPTDIR/OpenSSL"
else
    echo "    Rebuilding OpenSSL"
    # Download source code archive if not already in the project (-c option).
    cd $DOWNLOADDIR
    if [ ! -f $DOWNLOADDIR/$OPEN_SSL ]; then    
        wget -c $OPENSSL_SITE/$OPENSSL_FILE || true
    fi
    # Test source code integrity.
    if [ `openssl dgst -sha256 -hex $OPENSSL_FILE | cut -d " " --f 2` != \
        $OPENSSL_FILE_SHA256 ]
    then
        echo "File integrity check failed"
        exit
    fi
    
    # Expand the archive and cd into the OpenSSL project root.
    cd $WORKDIR
    rm -rf OpenSSL/* ; mkdir -p OpenSSL ; cd OpenSSL
    cp $DOWNLOADDIR/$OPENSSL_FILE  ./
    tar --extract -f $OPENSSL_FILE
    rm $OPENSSL_FILE
    cd *
    
    # Build OpenSSL
    # For shared library build use ... mingw shared  ...
    # For static build use ... mingw no-shared -static ...
    ./Configure mingw shared --cross-compile-prefix=i686-w64-mingw32- \
                --prefix=$WORKDIR/OpenSSL
    make build_programs
    make install_sw
    
    # Copy needed files to script directory.
    cd $SCRIPTDIR;  rm -rf OpenSSL ; mkdir -p OpenSSL
    # FIXME: be more selective
    cp -r $WORKDIR/OpenSSL/bin -t $SCRIPTDIR/OpenSSL
fi
cp -r $SCRIPTDIR/OpenSSL -t $WORKDIR/Mailpile

# GnuPG
#
# See build-aux/speedo.mk for targets and options.
# See https://wiki.gnupg.org/Build2.1_Windows
#
echo " "
echo "Get GnuPG"
if [ -e $SCRIPTDIR/GnuPG/gpg.exe ]; then
    echo "    Reusing previously built GnuPG"
    echo "    To force rebuild, delete $SCRIPTDIR/GnuPG"
else
    echo "    Rebuilding GnuPG"
    if [ ! -f $DOWNLOADDIR/$GNUPG_FILE_ALL ]; then
        # Consolidated source archive not in project. Download GnuPG source
        # archive and 3rd party source archives, build consolidated archive.
        cd $DOWNLOADDIR
        wget -c $GNUPG_SITE/$GNUPG_FILE || true
        # Test source code integrity.
        if [ `openssl dgst -sha1 -hex $GNUPG_FILE | cut -d " " --f 2` != \
            $GNUPG_FILE_SHA1 ]
        then
            echo "File integrity check failed"
            exit
        fi
        
        cd $WORKDIR
        rm -rf GnuPG/* ; mkdir -p GnuPG ; cd GnuPG
        mv $DOWNLOADDIR/$GNUPG_FILE  ./
        tar --extract -f $GNUPG_FILE
        rm $GNUPG_FILE
        cd *
        
        # The w32-source target downloads third party source packages
        # makes a consolidated archive containing GnuPG and 3rd party source
        # then builds the .dll and .exe.files
        # FIXME: Does speedo.mk check integrity of 3rd party source downloads?

        make -f build-aux/speedo.mk w32-source
        
        # Save the consolidated source archive for next time.
        mv $GNUPG_FILE_ALL $DOWNLOADDIR        
    else
        # Build from existing consolidated source archive.
        cd $WORKDIR
        rm -rf GnuPG/* ; mkdir -p GnuPG ; cd GnuPG
        cp $DOWNLOADDIR/$GNUPG_FILE_ALL  ./
        tar --extract -f $GNUPG_FILE_ALL
        rm $GNUPG_FILE_ALL
        cd *
        
        # The this-w32-source target uses 3rd party source
        # in the consolidated archive saved from last build.
        # then builds the .dll and .exe.files.       
        make -f build-aux/speedo.mk this-w32-source
    fi
    
    # Copy needed files to script directory.
    cd $SCRIPTDIR;  rm -rf GnuPG ; mkdir -p GnuPG
    cd $WORKDIR/GnuPG/*
    # FIXME: be more selective
    cp -r PLAY/inst/bin/* -t $SCRIPTDIR/GnuPG
fi
cp -r $SCRIPTDIR/GnuPG -t $WORKDIR/Mailpile


# Build the installer

echo " "
echo "Build installer"
cd $WORKDIR/Mailpile
makensis -V2 -NOCD -DVERSION=$VERSION -DPYTHON_FILE=$PYTHON_FILE \
                                                "$SCRIPTDIR/mailpile.nsi" 

# Save source code archive to publish for licence compliance.
cp -r $DOWNLOADDIR/* -t $SOURCEARCHIVEDIR

# Calculate SHA256 checksums for everything.
cd ..
openssl dgst -sha256 -hex Mailpile-$VERSION-Installer.exe SourceWin$VERSION/* \
     > Mailpile-$VERSION-dgst.txt

echo " "
echo "Version identifier:   $VERSION"
echo "Windows installer:    $WORKDIR/Mailpile-$VERSION-Installer.exe"
echo "Source code archive:  $SOURCEARCHIVEDIR"
echo "Integrity checks:     $WORKDIR/Mailpile-$VERSION-dgst.txt"
echo " "
sleep 5


      





