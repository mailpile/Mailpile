# Recipies for stuff
export PYTHONPATH := .

dev: tools
	@rm -f .SELF
	@ln -fs . .SELF
	@ln -fs scripts/mailpile mailpile.py
	@echo export PYTHONPATH=`pwd`

tools: scripts/breeder.py Makefile

scripts/breeder.py:
	@ln -fs ../../PyBreeder/breeder.py scripts/breeder.py

distclean: clean
	@rm -rvf dist/*.*

clean:
	@rm -vf *.pyc */*.pyc scripts/breeder.py mailpile.py .SELF
	@rm -vf .appver MANIFEST setup.cfg
	@rm -vrf *.egg-info build/
	@rm -vf debian/files debian/control debian/copyright debian/changelog
	@rm -vrf debian/pagekite* debian/python* debian/init.d

