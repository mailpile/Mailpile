FROM ubuntu:12.04

# Update packages lists
RUN apt-get update -y

# Force -y for apt-get
RUN echo "APT::Get::Assume-Yes true;" >>/etc/apt/apt.conf

# Add code & install the requirements
RUN apt-get install make python-pip
ADD Makefile /Mailpile/Makefile
WORKDIR /Mailpile
RUN make debian-dev

# Add code
ADD . /Mailpile

# Setup
RUN ./mp setup
RUN ./mp --set sys.http_host=0.0.0.0

CMD /Mailpile/mp www
EXPOSE 33411
VOLUME /.mailpile
