FROM mailpile

# Install C compiler for python deps w/ native extensions
RUN apk --no-cache add \
  gcc \
  libc-dev \
  python-dev \
  shadow

# Workaround: Setting mailpile users uid to 1000 to have write permissions
# from the docker host the to the shared volumes /Mailpile and /mailpile-data.
# Mounted volumes seem to be configured w/ uid/guid = 1000.
# Learn more here:
# - https://github.com/docker/docker/issues/7198
# - https://denibertovic.com/posts/handling-permissions-with-docker-volumes/
RUN usermod -u 1000 mailpile

RUN pip install -r requirements-dev.txt

RUN chmod +x /entrypoint.sh

CMD ["./mp"]
