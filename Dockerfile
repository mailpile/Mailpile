FROM ubuntu:14.04

# Install dependencies
RUN apt-get update -y && \
    apt-get install -y openssl python-imaging python-jinja2 python-lxml libxml2-dev libxslt1-dev python-pgpdump spambayes

# Add code
WORKDIR /Mailpile
ADD . /Mailpile

# Create users and groups
RUN groupadd -r mailpile \
    && mkdir -p /mailpile-data/.gnupg \
    && useradd -r -d /mailpile-data -g mailpile mailpile

# Add GnuPG placeholder file
RUN touch /mailpile-data/.gnupg/docker_placeholder

# Fix permissions
RUN chown -R mailpile:mailpile /Mailpile
RUN chown -R mailpile:mailpile /mailpile-data

# Run as non-privileged user
USER mailpile

# Initialize mailpile
RUN ./mp setup

# Entrypoint
CMD ./mp --www=0.0.0.0:33411 --wait
EXPOSE 33411

# Volumes
VOLUME /mailpile-data/.local/share/Mailpile
VOLUME /mailpile-data/.gnupg
