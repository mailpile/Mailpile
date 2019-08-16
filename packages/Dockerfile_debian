# ----------------------------------------------------------------------------#
# This Dockerfile creates a Debian package for mailpile.                      #
#                                                                             #
# Usage: cd .. && make dpkg                                                   #
# ----------------------------------------------------------------------------#
FROM debian:stretch
MAINTAINER Alexandre Viau <aviau@debian.org>

# The big list below is a subset of what we get from mk-build-deps; manually
# copied so the Docker intermediate images will change a little bit less when
# the Debian package rules themselves get updated. Less wasted bandwidth,
# quicker development cycles...
RUN apt-get update && \
    apt-get install -y -qq software-properties-common \
                           build-essential \
                           debhelper \
                           devscripts \
                           equivs \
  python-all python-bs4 python-dns python-funcsigs \
  python-jinja2 python-lxml python-markupsafe \
  python-mock python-nose python-pbr python-pgpdump \
  python-pil python-selenium python-setuptools python-webencodings \
  python-socksipychain xdg-utils

RUN mkdir /root/mailpile /mnt/dist
COPY packages/debian /root/mailpile/debian
COPY dist/version.txt /root/mailpile-version.txt
VOLUME /mnt/dist

RUN ln -s /mnt/dist/mailpile.tar.gz /root/mailpile_$(cat /root/mailpile-version.txt).orig.tar.gz
RUN sed -i "s|<-- version -->|$(cat /root/mailpile-version.txt)-1|" /root/mailpile/debian/changelog

RUN mk-build-deps --install /root/mailpile/debian/control --tool "apt-get --force-yes -y"

WORKDIR /root/mailpile
ENV DESTINATION_DPKG_DIR /mnt/dist
CMD tar xvf ../mailpile_$(cat /root/mailpile-version.txt).orig.tar.gz -C ./ \
    && dpkg-buildpackage -us -uc -b \
    && cp ../*.deb /mnt/dist
