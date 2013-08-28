# Recipies for stuff
export PYTHONPATH := .

dev: tools
	@rm -f .SELF
	@ln -fs . .SELF
	@echo export PYTHONPATH=`pwd`

combined:
	@./scripts/breeder.py static \
                     	mailpile/__init__.py \
			mailpile/util.py \
			mailpile/mailutils.py \
			mailpile/ui.py \
			mailpile/commands.py \
			mailpile/httpd.py \
			mailpile/app.py \
                     >mailpile-tmp.py
	@chmod +x mailpile-tmp.py
	@mv mailpile-tmp.py dist/mailpile-`python setup.py --version`.py
	@ls -l dist/mailpile-*.py

tools: scripts/breeder.py Makefile

scripts/breeder.py:
	@ln -fs ../../Beanstalks/PyBreeder/breeder.py scripts/breeder.py

distclean: clean
	@rm -rvf dist/*.*

clean:
	@rm -vf *.pyc */*.pyc mailpile-tmp.py scripts/breeder.py mailpile.py
	@rm -vf .appver MANIFEST setup.cfg .SELF
	@rm -vrf *.egg-info build/
	@rm -vf debian/files debian/control debian/copyright debian/changelog
	@rm -vrf debian/pagekite* debian/python* debian/init.d

