# Recipes for stuff
export PYTHONPATH := .

all:	alltests docs web compilemessages

dev:
	@echo export PYTHONPATH=`pwd`

arch-dev:
	sudo pacman -Syu community/python2-pillow extra/python2-lxml community/python2-jinja \
	                 community/python2-pep8 extra/python2-nose community/phantomjs \
	                 extra/python2-pip community/python2-mock \
	                 extra/ruby
	TMPDIR=`mktemp -d /tmp/aur.XXXXXXXXXX`; \
	cd $$TMPDIR; \
	pacman -Qs '^yuicompressor$$' > /dev/null; \
	if [ $$? -ne 0 ]; then \
	  curl -s https://aur.archlinux.org/packages/yu/yuicompressor/yuicompressor.tar.gz | tar xzv; \
	  cd yuicompressor; \
	  makepkg -si; \
	  cd $$TMPDIR; \
	fi; \
	  pacman -Qs '^spambayes$$' > /dev/null; \
	  if [ $$? -ne 0 ]; then \
	  curl -s https://aur.archlinux.org/packages/sp/spambayes/spambayes.tar.gz | tar xzv; \
	  cd spambayes; \
	  makepkg -si; \
	fi; \
	cd /tmp; \
	rm -rf $$TMPDIR
	sudo pip2 install 'selenium>=2.40.0'
	which lessc >/dev/null || sudo gem install therubyracer less
	which bower >/dev/null || sudo npm install -g bower
	which uglify >/dev/null || sudo npm install -g uglify

fedora-dev:
	sudo yum install python-imaging python-lxml python-jinja2 python-pep8 \
	                     ruby-devel python-yui python-nose spambayes \
	                     phantomjs python-pip python-mock npm
	sudo yum install rubygems; \
	sudo yum install python-pgpdump || pip install pgpdump
	sudo pip install 'selenium>=2.40.0'
	which lessc >/dev/null || sudo gem install therubyracer less
	which bower >/dev/null || sudo npm install -g bower
	which uglify >/dev/null || sudo npm install -g uglify

debian-dev:
	sudo apt-get install python-imaging python-lxml python-jinja2 pep8 \
	                     ruby-dev yui-compressor python-nose spambayes \
	                     phantomjs python-pip python-mock npm
	if [ "$(shell cat /etc/debian_version)" = "jessie/sid"  ]; then\
		sudo apt-get install rubygems-integration;\
	else \
		sudo apt-get install rubygems; \
	fi
	sudo apt-get install python-pgpdump || pip install pgpdump
	sudo pip install 'selenium>=2.40.0'
	which lessc >/dev/null || sudo gem install therubyracer less
	which bower >/dev/null || sudo npm install -g bower
	which uglify >/dev/null || sudo npm install -g uglify

docs:
	@test -d doc || \
           git submodule update --remote
	@python2 mailpile/urlmap.py |grep -v ^FIXME: >doc/URLS.md
	@ls -l doc/URLS.md
	@python2 mailpile/defaults.py |grep -v -e ^FIXME -e ';timestamp' \
           >doc/defaults.cfg
	@ls -l doc/defaults.cfg

web: less js
	@true

alltests: clean pytests
	@chmod go-rwx mailpile/tests/data/gpg-keyring
	@python2 scripts/mailpile-test.py || true
	@nosetests

pytests:
	@echo -n 'urlmap           ' && python2 mailpile/urlmap.py -nomap
	@echo -n 'search           ' && python2 mailpile/search.py
	@echo -n 'mailutils        ' && python2 mailpile/mailutils.py
	@echo -n 'config           ' && python2 mailpile/config.py
	@echo -n 'conn_brokers     ' && python2 mailpile/conn_brokers.py
	@echo -n 'util             ' && python2 mailpile/util.py
	@echo -n 'vcard            ' && python2 mailpile/vcard.py
	@echo -n 'workers          ' && python2 mailpile/workers.py
	@echo -n 'mailboxes/pop3   ' && python2 mailpile/mailboxes/pop3.py
	@echo -n 'mail_source/imap ' && python2 mailpile/mail_source/imap.py
	@echo 'crypto/streamer...'   && python2 mailpile/crypto/streamer.py
	@echo

clean:
	@rm -f `find . -name \\*.pyc` \
	       `find . -name \\*.mo` \
               mailpile-tmp.py mailpile.py \
	       .appver MANIFEST setup.cfg .SELF .*deps \
	       scripts/less-compiler.mk ghostdriver.log
	@rm -rf *.egg-info build/ mp-virtualenv/ \
               mailpile/tests/data/tmp/ testing/tmp/

mrproper: clean
	@rm -rf dist/ bower_components/

sdist: clean
	@python setup.py sdist

#bdist-prep: compilemessages web -- FIXME: Make building web assets work!
bdist-prep: compilemessages
	@true

bdist:
	@python setup.py bdist

virtualenv:
	virtualenv -p python2 mp-virtualenv
	bash -c 'source mp-virtualenv/bin/activate && pip install -r requirements.txt && python setup.py install'

js:
	bower install
	# Warning: Horrible hack to extract rules from Gruntfile.js
	cat `cat Gruntfile.js \
                |sed -e '1,/concat:/d ' \
                |sed -e '1,/src:/d' -e '/dest:/,$$d' \
                |grep / \
                |sed -e "s/[',]/ /g"` \
          >> mailpile/www/default/js/mailpile-min.js.tmp
	uglify -s mailpile/www/default/js/mailpile-min.js.tmp \
                  mailpile/www/default/js/mailpile-min.js
	@rm -f mailpile/www/default/js/mailpile-min.js.tmp

less: less-compiler
	@make -s -f scripts/less-compiler.mk

less-loop: less-compiler
	@echo 'Running less compiler every 15 seconds. CTRL+C quits.'
	@while [ 1 ]; do \
                make -s less; \
                sleep 15; \
        done

less-compiler:
	@cp scripts/less-compiler.in scripts/less-compiler.mk
	@find mailpile/www/default/less/ -name '*.less' \
                |perl -npe s'/^/\t/' \
		|perl -npe 's/$$/\\/' \
                >>scripts/less-compiler.mk
	@echo >> scripts/less-compiler.mk
	@perl -e 'print "\t\@touch .less-deps", $/' >> scripts/less-compiler.mk

genmessages:
	@scripts/make-messages.sh

compilemessages:
	@scripts/compile-messages.sh
