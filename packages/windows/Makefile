all: GnuPG OpenSSL Python27
	@echo "=== Making Nullsoft Installer package."
	#makensis mailpile.nsi
	@echo "FIXME"

GnuPG:
	@echo "=== Building GnuPG for Windows."
	sudo apt-get install wine mingw32
	@mkdir -p Downloads
	@(cd Downloads \
          && wget -q -c ftp://ftp.gnupg.org/gcrypt/gnupg/gnupg-1.4.18.tar.bz2)
	[ "$$(sha1sum Downloads/gnupg-1.4.18.tar.bz2 |cut -f1 -d\ )" \
          = "41462d1a97f91abc16a0031b5deadc3095ce88ae" ]
	@tar xfj Downloads/gnupg-1.4.18.tar.bz2
	@(cd gnupg-1.4.18 \
          && ./scripts/autogen.sh \
          && ./scripts/build-w32 \
          && make \
          || [ -e gnupg-1.4.18/g10/gpg.exe ])
	@mkdir -p GnuPG
	@mv -v gnupg-1.4.18/g10/gpg.exe GnuPG
	@rm -rf gnupg-1.4.18

OpenSSL:
	@echo "=== Building OpenSSL for Windows."
	@echo "FIXME"

Python27:
	@echo "=== Building Python for Windows."
	@echo "FIXME"

clean:
	@rm -rf GnuPG OpenSSL Python27 gnupg-1.4.18

distclean: clean
	@rm -rf Downloads "Mailpile Installer.exe"
