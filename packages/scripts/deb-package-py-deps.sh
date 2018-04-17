#!/bin/bash
#
# This is a quick'n'dirty shell script to build packages for some of
# the Python packages we depend on, but aren't yet in Debian.
#
ALL_PACKAGES="imgsize gui-o-matic"


# Bail on errors
set -e

# Start fresh!
rm -rf src dist


mkdir -p src
cd src

    # Pull things from PyPI
    pypi-download --release=2.0 imgsize

    # Pull things from Github
    git clone https://github.com/mailpile/gui-o-matic  # FIXME: version?

cd ..


mkdir -p dist
for package in $ALL_PACKAGES; do

    if [ -d src/$package ]; then
        cd src/$package
        python setup.py --command-packages=stdeb.command bdist_deb
        cd ../..
        mv -v src/$package/deb_dist/*.deb dist/
    else
        py2dsc-deb \
            -m "Mailpile Team <packages@mailpile.is>" \
            src/$package*.tar.gz
        mv -v deb_dist/*.deb dist/
        rm -rf deb_dist
    fi

done

dpkg-sig --sign builder dist/*deb
cat <<tac
Packages built!

Now, please run one or more of these to publish the results:

    cp dist/*.deb ~/incoming/nightly
    cp dist/*.deb ~/incoming/stable

tac
