FROM ubuntu:14.04

RUN apt-get update -y
RUN apt-get install -y openssl python-imaging python-jinja2 python-lxml libxml2-dev libxslt1-dev python-pgpdump

WORKDIR /Mailpile
ADD . /Mailpile

RUN	groupadd -r mailpile \
&&  mkdir /mailpile-data \
&&	useradd -r -d /mailpile-data -g mailpile mailpile

RUN chown -R mailpile:mailpile /Mailpile
RUN chown -R mailpile:mailpile /mailpile-data

USER mailpile

RUN ./mp setup

CMD ./mp --www=0.0.0.0:33411 --wait
EXPOSE 33411

VOLUME /mailpile-data/.local/share/Mailpile
VOLUME /mailpile-data/.gnupg
