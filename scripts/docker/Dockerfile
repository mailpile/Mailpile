# Mailpile
#
# VERSION 0.1

FROM base

RUN apt-get install -y python-lxml python-gnupginterface git make
RUN git clone https://github.com/pagekite/Mailpile.git
ADD start.sh /start.sh

CMD ./start.sh

EXPOSE 33411:33411
