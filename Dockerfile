FROM alpine:3.5

WORKDIR /Mailpile

# Create users and groups
RUN addgroup -S mailpile && adduser -S -h /mailpile-data -G mailpile mailpile

# Initialize mailpile
# RUN chown mailpile: /mailpile-data -R && ./mp setup

# Volumes
VOLUME /mailpile-data/.local/share/Mailpile
VOLUME /mailpile-data/.gnupg

# Install dependencies
RUN apk --no-cache add \
	ca-certificates \
	openssl \
	gnupg1 \
	py-pip \
	py-imaging \
	py-jinja2 \
	py-lxml \
	py-lockfile \
	py-pillow \
	py-pbr \
	py-cryptography \
	su-exec

ADD requirements.txt /Mailpile/requirements.txt
RUN pip install -r requirements.txt

# Entrypoint
ADD packages/docker/entrypoint.sh /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
CMD ./mp --www=0.0.0.0:33411 --wait
EXPOSE 33411

# Add code
ADD . /Mailpile

