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
	                     python-pip python-mock python-selenium \
						 rubygems-integration
	dpkg -l|grep -qP ' nodejs .*nodesource' || sudo apt install npm
	sudo apt-get install python-pgpdump || pip install pgpdump
	which phantomjs >/dev/null || sudo apt-get install phantomjs || sudo npm install -g phantomjs
	which lessc >/dev/null || sudo gem install therubyracer less
	which bower >/dev/null || sudo npm install -g bower
	which uglify >/dev/null || sudo npm install -g uglify


submodules:
	git submodule update --remote

docs: submodules
	@python2.7 mailpile/urlmap.py |grep -v ^FIXME: >doc/URLS.md
	@ls -l doc/URLS.md
	@python2.7 mailpile/defaults.py |grep -v -e ^FIXME -e ';timestamp' \
           >doc/defaults.cfg
	@ls -l doc/defaults.cfg

web: less js
	@true

alltests: clean pytests
	@chmod go-rwx mailpile/tests/data/gpg-keyring
	@DISPLAY= nosetests
	@DISPLAY= python2.7 scripts/mailpile-test.py || true
	@git checkout mailpile/tests/data/

pytests:
	@echo -n 'security         ' && python2.7 mailpile/security.py
	@echo -n 'urlmap           ' && python2.7 mailpile/urlmap.py -nomap
	@echo -n 'search           ' && python2.7 mailpile/search.py
	@echo -n 'mailboxes.mbox   ' && python2.7 mailpile/mailboxes/mbox.py
	@echo -n 'mailutils.safe   ' && python2.7 mailpile/mailutils/safe.py
	@echo -n 'mailutils.addrs  ' && python2.7 mailpile/mailutils/addresses.py
	@echo -n 'mailutils.emails ' && python2.7 mailpile/mailutils/emails.py
	@echo -n 'config/base      ' && python2.7 mailpile/config/base.py
	@echo -n 'config/validators' && python2.7 mailpile/config/validators.py
	@echo -n 'config/manager   ' && python2.7 mailpile/config/manager.py
	@echo -n 'conn_brokers     ' && python2.7 mailpile/conn_brokers.py
	@echo -n 'crypto/autocrypt ' && python2.7 mailpile/crypto/autocrypt.py
	@echo -n 'plug...autocrypt ' && python2.7 mailpile/plugins/crypto_autocrypt.py
	@echo -n 'crypto/mime      ' && python2.7 mailpile/crypto/mime.py
	@echo -n 'index.base       ' && python2.7 mailpile/index/base.py
	@echo -n 'index.msginfo    ' && python2.7 mailpile/index/msginfo.py
	@echo -n 'index.mailboxes  ' && python2.7 mailpile/index/mailboxes.py
	@echo -n 'index.search     ' && python2.7 mailpile/index/search.py
	@echo -n 'util             ' && python2.7 mailpile/util.py
	@echo -n 'vcard            ' && python2.7 mailpile/vcard.py
	@echo -n 'workers          ' && python2.7 mailpile/workers.py
	@echo -n 'packing          ' && python2.7 mailpile/packing.py
	@echo -n 'mailboxes/pop3   ' && python2.7 mailpile/mailboxes/pop3.py
	@echo -n 'mail_source/imap ' && python2.7 mailpile/mail_source/imap.py
	@echo -n 'crypto/aes_utils ' && python2.7 mailpile/crypto/aes_utils.py
	@echo 'spambayes...        ' && python2.7 mailpile/spambayes/Tester.py
	@echo 'crypto/streamer...'   && python2.7 mailpile/crypto/streamer.py
	@echo

clean:
	@rm -f `find . -name \\*.pyc` \
	       `find . -name \\*.pyo` \
	       `find . -name \\*.mo` \
	        mailpile-tmp.py mailpile.py \
	        ChangeLog AUTHORS \
	        .appver MANIFEST .SELF .*deps \
                dist/*.tar.gz dist/*.deb dist/*.rpm \
	        scripts/less-compiler.mk ghostdriver.log
	@rm -rf *.egg-info build/ \
               mailpile/tests/data/tmp/ testing/tmp/
	@rm -f shared-data/multipile/www/admin.cgi

mrproper: clean
	@rm -rf shared-data/locale/?? shared-data/locale/??[_@]*
	@rm -rf bower_components/ shared-data/locale/mailpile.pot
	@rm -rf mp-virtualenv/
	git reset --hard && git clean -dfx

sdist: clean
	@python setup.py sdist

#bdist-prep: compilemessages web -- FIXME: Make building web assets work!
bdist-prep: compilemessages
	@true

bdist:
	@python setup.py bdist_wheel

virtualenv: mp-virtualenv/bin/activate
virtualenv-dev: mp-virtualenv/bin/.dev

mp-virtualenv/bin/activate:
	virtualenv -p python2.7 --system-site-packages mp-virtualenv
	bash -c 'source mp-virtualenv/bin/activate && pip install -r requirements.txt && python setup.py install'
	@rm -rf mp-virtualenv/bin/.dev
	@echo
	@echo NOTE: If you want to test/develop with GnuPG 2.1, you might
	@echo       want to activate the virtualenv and then run this script
	@echo to build GnuPG 2.1: ./scripts/add-gpgme-and-gnupg-to-venv
	@echo

mp-virtualenv/bin/.dev: virtualenv
	rm -rf mp-virtualenv/lib/python2.7/site-packages/mailpile
	cd mp-virtualenv/lib/python2.7/site-packages/ && ln -s ../../../../mailpile
	rm -rf mp-virtualenv/share/mailpile
	cd mp-virtualenv/share/ && ln -s ../../shared-data mailpile
	@touch mp-virtualenv/bin/.dev

bower_components:
	@bower install

js: bower_components
	# Warning: Horrible hack to extract rules from Gruntfile.js
	@rm -f shared-data/default-theme/js/libraries.min.js
	@rm -f shared-data/default-theme/js/mailpile-min.js.tmp*
	@cat Gruntfile.js \
                |sed -e '1,/concat:/d ' \
                |sed -e '1,/src:/d' -e '/dest:/,$$d' \
                |grep / \
                |sed -e "s/[',]/ /g" \
            |xargs sed -e '$$a;' \
            >> shared-data/default-theme/js/mailpile-min.js.tmp
	@uglify -s shared-data/default-theme/js/mailpile-min.js.tmp \
               -o shared-data/default-theme/js/mailpile-min.js.tmp2
	@sed -e "s/@MP_JSBUILD_INFO@/`./scripts/gitwhere.sh`/" \
	    < shared-data/default-theme/js/libraries.js \
	    > shared-data/default-theme/js/libraries.min.js
	@echo '/* Sources...' \
	    >> shared-data/default-theme/js/libraries.min.js
	@bower --offline --no-color list \
	    >> shared-data/default-theme/js/libraries.min.js
	@echo '*/' \
	    >> shared-data/default-theme/js/libraries.min.js
	@cat shared-data/default-theme/js/mailpile-min.js.tmp2 \
            >> shared-data/default-theme/js/libraries.min.js
	@rm -f shared-data/default-theme/js/mailpile-min.js.tmp*

less: less-compiler bower_components
	@cp -fa \
                bower_components/select2/select2.png \
                bower_components/select2/select2x2.png \
                bower_components/select2/select2-spinner.gif \
            shared-data/default-theme/css/
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
	tx pull -a --minimum-perc=25
	tx pull -l is,en_GB


# -----------------------------------------------------------------------------
# BUILD
# -----------------------------------------------------------------------------

dist/version.txt: mailpile/config/defaults.py scripts/version.py
	mkdir -p dist
	scripts/version.py > dist/version.txt

dist/mailpile.tar.gz: mrproper genmessages transifex dist/version.txt
	git submodule update --init --recursive
	git submodule foreach 'git reset --hard && git clean -dfx'
	mkdir -p dist
	scripts/version.py > dist/version.txt
	tar --exclude='./packages/debian' --exclude=dist --exclude-vcs -czf dist/mailpile-$$(cat dist/version.txt).tar.gz -C $(shell pwd) .
	(cd dist; ln -fs mailpile-$$(cat version.txt).tar.gz mailpile.tar.gz)

.dockerignore: dist/version.txt packages/Dockerfile_debian packages/debian packages/debian/rules
	mkdir -p dist
	docker build \
	    --file=packages/Dockerfile_debian \
	    --tag=mailpile-deb-builder \
	    ./
	touch .dockerignore

dpkg: dist/mailpile.tar.gz .dockerignore
	docker run \
	    --rm --volume=$$(pwd)/dist:/mnt/dist \
	    mailpile-deb-builder
