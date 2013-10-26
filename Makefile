# Recipies for stuff
export PYTHONPATH := .

all:	docs alltests dev web

dev:
	@echo export PYTHONPATH=`pwd`

debian-dev:
	sudo apt-get install python-imaging python-lxml python-jinja2 \
	                     python-gnupginterface \
	                     rubygems ruby-dev yui-compressor
	sudo gem install therubyracer less

docs:
	python mailpile/urlmap.py >doc/URLS.md
	python mailpile/defaults.py |grep -v ';timestamp' >doc/defaults.cfg

web: less
	@true

alltests:
	python mailpile/config.py \
	&& python mailpile/util.py \
	&& python mailpile/workers.py \
	&& scripts/mailpile-test.py \

clean:
	@rm -vf *.pyc */*.pyc */*/*.pyc mailpile-tmp.py mailpile.py
	@rm -vf .appver MANIFEST setup.cfg .SELF .*deps
	@rm -vf scripts/less-compiler.mk
	@rm -vrf *.egg-info build/ mp-virtualenv/ dist/

virtualenv:
	virtualenv mp-virtualenv
	bash -c 'source mp-virtualenv/bin/activate && pip install -r requirements.txt && python setup.py install'

less: less-compiler
	make -f scripts/less-compiler.mk

less-compiler:
	@cp scripts/less-compiler.in scripts/less-compiler.mk
	@find static/default/less/ -name '*.less' \
                |sed -e s'/^/\t/' -e 's/$$/\\/' \
                >>scripts/less-compiler.mk
	@echo >> scripts/less-compiler.mk
	@echo '\t@touch .less-deps' >> scripts/less-compiler.mk
