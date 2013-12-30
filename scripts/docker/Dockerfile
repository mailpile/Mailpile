# Mailpile
#
# VERSION 0.1

FROM ubuntu

RUN apt-get install -y python-lxml python-imaging python-jinja2 git make
RUN git clone https://github.com/pagekite/Mailpile.git
ADD start.sh /start.sh

CMD ./start.sh

EXPOSE 33411
