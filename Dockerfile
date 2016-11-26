FROM ubuntu:16.04
MAINTAINER Aleksandar Todorović <aleksandar@r3bl.me>

# Install dependencies
RUN apt-get update -y && \
    apt-get install -y tor python openssl python-imaging git python-jinja2 python-lxml libxml2-dev libxslt1-dev python-pgpdump spambayes python-pip && \
    apt-get upgrade -y

# Add code
RUN git clone --recursive https://github.com/mailpile/Mailpile/ Mailpile
WORKDIR "/Mailpile"

# Create users and groups
RUN groupadd -r mailpile \
    && mkdir -p /mailpile-data/.gnupg \
    && useradd -r -d /mailpile-data -g mailpile mailpile

# Add GnuPG placeholder file
RUN touch /mailpile-data/.gnupg/docker_placeholder

# Fix permissions
RUN chown -R mailpile:mailpile /Mailpile
RUN chown -R mailpile:mailpile /mailpile-data

# Install pip requirements
RUN pip install -r requirements.txt

# Initialize mailpile
RUN ./mp setup

# Entrypoint
EXPOSE 33411

# Volumes
VOLUME /mailpile-data/.local/share/Mailpile
VOLUME /mailpile-data/.gnupg

ENV MAILPILE_HOME=/mailpile-data/.local/share/Mailpile/
CMD ["./mp", "--www=0.0.0.0:33411", "--wait"]
