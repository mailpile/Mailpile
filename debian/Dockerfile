# ----------------------------------------------------------------------------#
# This Dockerfile creates a Debian package for mailpile.                      #
#                                                                             #
# Usage: cd .. && make dpkg                                                   #
# ----------------------------------------------------------------------------#
FROM ubuntu:14.04
MAINTAINER Matthew Power <mth.power@gmail.com>

RUN apt-get update && apt-get install -y -qq software-properties-common
RUN add-apt-repository ppa:dh-virtualenv/stable
RUN apt-get update && apt-get install -y -qq build-essential debhelper devscripts equivs

ADD ./ /root/mailpile

RUN apt-get update && mk-build-deps --install /root/mailpile/debian/control --tool "apt-get --force-yes -y"

RUN mkdir /mnt/dist
VOLUME /mnt/dist

WORKDIR /root/mailpile

ENV DH_VIRTUALENV_INSTALL_ROOT /opt/mailpile
ENV DESTINATION_DPKG_DIR /mnt/dist
CMD ["dpkg-buildpackage", "-us", "-uc", "-b", "--changes-option=-u/mnt/dist"]
