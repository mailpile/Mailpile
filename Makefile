# Recipes for stuff
export PYTHONPATH := .

help:
	@echo ""
	@echo "BUILD"
	@echo "    dpkg"
	@echo "        Create a debian package of this service (in a Docker "
	@echo "        container)."
	@echo ""


all:	submodules alltests docs web compilemessages transifex

dev:
	@echo export PYTHONPATH=`pwd`

arch-dev:
	sudo pacman -Syu --needed community/python2-pillow extra/python2-lxml community/python2-jinja \
	                 community/python2-pep8 extra/python2-nose community/phantomjs \
	                 extra/python2-pip community/python2-mock \
	                 extra/ruby community/npm community/spambayes
	TMPDIR=`mktemp -d /tmp/aur.XXXXXXXXXX`; \
	cd $$TMPDIR; \
	pacman -Qs '^yuicompressor$$' > /dev/null; \
	if [ $$? -ne 0 ]; then \
	  sudo pacman -S --needed core/base-devel; \
	  curl -s https://aur.archlinux.org/cgit/aur.git/snapshot/yuicompressor.tar.gz | tar xzv; \
	  cd yuicompressor; \
	  makepkg -si; \
	  cd $$TMPDIR; \
	fi; \
	cd /tmp; \
	rm -rf $$TMPDIR
	sudo pip2 install 'selenium>=2.40.0'
	which lessc >/dev/null || sudo gem install therubyracer less
	which bower >/dev/null || sudo npm install -g bower
	which uglify >/dev/null || sudo npm install -g uglify

fedora-dev:
	sudo yum install python-imaging python-lxml python-jinja2 python-pep8 \
	                     ruby ruby-devel python-yui python-nose spambayes \
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
	                     phantomjs python-pip python-mock python-selenium npm
	if [ "$(shell cat /etc/debian_version)" = "jessie/sid"  ]; then\
		sudo apt-get install rubygems-integration;\
	else \
		sudo apt-get install rubygems; \
	fi
	sudo apt-get install python-pgpdump || pip install pgpdump
	which lessc >/dev/null || sudo gem install therubyracer less
	which bower >/dev/null || sudo npm install -g bower
	which uglify >/dev/null || sudo npm install -g uglify


submodules:
	git submodule update --remote

docs: submodules
	@python2 mailpile/urlmap.py |grep -v ^FIXME: >doc/URLS.md
	@ls -l doc/URLS.md
	@python2 mailpile/defaults.py |grep -v -e ^FIXME -e ';timestamp' \
           >doc/defaults.cfg
	@ls -l doc/defaults.cfg

web: less js
	@true

alltests: clean pytests
	@chmod go-rwx mailpile/tests/data/gpg-keyring
	@DISPLAY= nosetests
	@DISPLAY= python2 scripts/mailpile-test.py || true
	@git checkout mailpile/tests/data/

pytests:
	@echo -n 'security         ' && python2 mailpile/security.py
	@echo -n 'urlmap           ' && python2 mailpile/urlmap.py -nomap
	@echo -n 'search           ' && python2 mailpile/search.py
	@echo -n 'mailutils        ' && python2 mailpile/mailutils/__init__.py
	@echo -n 'mailutils.safe   ' && python2 mailpile/mailutils/safe.py
	@echo -n 'config/base      ' && python2 mailpile/config/base.py
	@echo -n 'config/validators' && python2 mailpile/config/validators.py
	@echo -n 'config/manager   ' && python2 mailpile/config/manager.py
	@echo -n 'conn_brokers     ' && python2 mailpile/conn_brokers.py
	@echo -n 'index.base       ' && python2 mailpile/index/base.py
	@echo -n 'index.msginfo    ' && python2 mailpile/index/msginfo.py
	@echo -n 'index.mailboxes  ' && python2 mailpile/index/mailboxes.py
	@echo -n 'index.search     ' && python2 mailpile/index/search.py
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
	        ChangeLog AUTHORS \
	        .appver MANIFEST .SELF .*deps \
	        scripts/less-compiler.mk ghostdriver.log
	@rm -rf *.egg-info build/ mp-virtualenv/ \
               mailpile/tests/data/tmp/ testing/tmp/
	@rm -f shared-data/multipile/www/admin.cgi

mrproper: clean
	@rm -rf shared-data/locale/?? shared-data/locale/??[_@]*
	@rm -rf dist/ bower_components/ shared-data/locale/mailpile.pot
	git reset --hard && git clean -dfx

sdist: clean
	@python setup.py sdist

#bdist-prep: compilemessages web -- FIXME: Make building web assets work!
bdist-prep: compilemessages
	@true

bdist:
	@python setup.py bdist_wheel

virtualenv:
	virtualenv -p python2 mp-virtualenv
	bash -c 'source mp-virtualenv/bin/activate && pip install -r requirements.txt && python setup.py install'

bower_components:
	@bower install

js: bower_components
	# Warning: Horrible hack to extract rules from Gruntfile.js
	rm -f shared-data/default-theme/js/libraries.min.js
	cat `cat Gruntfile.js \
                |sed -e '1,/concat:/d ' \
                |sed -e '1,/src:/d' -e '/dest:/,$$d' \
                |grep / \
                |sed -e "s/[',]/ /g"` \
          >> shared-data/default-theme/js/mailpile-min.js.tmp
	uglify -s shared-data/default-theme/js/mailpile-min.js.tmp \
               -o shared-data/default-theme/js/libraries.min.js
	#@cp -va shared-data/default-theme/js/mailpile-min.js.tmp \
        #        shared-data/default-theme/js/libraries.min.js
	@rm -f shared-data/default-theme/js/mailpile-min.js.tmp

less: less-compiler bower_components
	@make -s -f scripts/less-compiler.mk

less-loop: less-compiler
	@echo 'Running less compiler every 15 seconds. CTRL+C quits.'
	@while [ 1 ]; do \
                make -s less; \
                sleep 15; \
        done

less-compiler:
	bower install
	@cp scripts/less-compiler.in scripts/less-compiler.mk
	@find shared-data/default-theme/less/ -name '*.less' \
                |perl -npe s'/^/\t/' \
		|perl -npe 's/$$/\\/' \
                >>scripts/less-compiler.mk
	@echo >> scripts/less-compiler.mk
	@perl -e 'print "\t\@touch .less-deps", $/' >> scripts/less-compiler.mk

genmessages:
	@scripts/make-messages.sh

compilemessages:
	@scripts/compile-messages.sh

transifex:
	tx pull -a --minimum-perc=50
	tx pull -l is,en_GB


# -----------------------------------------------------------------------------
# BUILD
# -----------------------------------------------------------------------------

tarball: mrproper js genmessages transifex
	git submodule update --init --recursive
	git submodule foreach 'git reset --hard && git clean -dfx'
	tar --exclude='./packages/debian' --exclude-vcs -czf /tmp/mailpile.tar.gz -C $(shell pwd) .
	mv /tmp/mailpile.tar.gz .

dpkg: tarball
	if [ ! -d dist ]; then \
	    mkdir dist; \
	fi;
	if [ -e ./dist/*.deb ]; then \
	    sudo rm ./dist/*.deb; \
	fi;
	sudo docker build \
	    --file=packages/Dockerfile_debian \
	    --tag=mailpile-deb-builder \
	    ./
	sudo docker run \
	    --volume=$$(pwd)/dist:/mnt/dist \
	    mailpile-deb-builder
