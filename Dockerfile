FROM ubuntu:16.10

# Install dependencies
RUN apt-get update -y && \
    apt-get install -y openssl \
                       python-pip \
                       python-imaging \
                       python-jinja2 \
                       python-lxml \
                       libxml2-dev \
                       libxslt1-dev \
                       python-pgpdump \
                       python-cryptography \
                       spambayes \
                       tor

# Add mailpile code (required for initial setup, not for develpoment)
ADD . /Mailpile

# Create data dir
# This will be overriden by a volume hosted by the docker host (your dev machine)
RUN mkdir /mailpile-data

# Create mailpile user and group.
RUN groupadd -r mailpile && \
    useradd -r -d /mailpile-data -g mailpile mailpile

# Workaround: Setting mailpile users uid to 1000 to have write permissions
# from the docker host the to the shared volumes /Mailpile and /mailpile-data.
# Mounted volumes seem to be configured w/ uid/guid = 1000.
# Learn more here:
# - https://github.com/docker/docker/issues/7198
# - https://denibertovic.com/posts/handling-permissions-with-docker-volumes/
RUN usermod -u 1000 mailpile

# Fix permissions for dirs (w/o they would only be accessible for root)
RUN chown -R mailpile:mailpile /Mailpile
RUN chown -R mailpile:mailpile /mailpile-data

# Set /Mailpile as root dir for further RUN cmds
WORKDIR /Mailpile

RUN pip install --upgrade pip
RUN pip install -r requirements-dev.txt

# Run as mailpile user
USER mailpile

# Initialize mailpile
RUN ./mp setup

CMD ["./mp", "--www=0.0.0.0:33411", "--wait"]
EXPOSE 33411
