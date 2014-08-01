

all: gnupg openssl python
	@echo "Making Nullsoft Installer package."
	makensis mailpile.nsi

getbinaries:
	wget http://slproweb.com/download/Win32OpenSSL_Light-1_0_1h.exe
	wget http://files.gpg4win.org/gpg4win-light-2.2.1.exe
	wget https://www.python.org/ftp/python/3.4.1/python-3.4.1.msi

gnupg:
	@echo "Building GnuPG for Windows."

openssl:
	@echo "Building OpenSSL for Windows."

python:
	@echo "Building Python for Windows."

clean:
	rm "Mailpile Installer.exe"
