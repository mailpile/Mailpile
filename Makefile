# Recipies for stuff
export PYTHONPATH := .

dev:
	@echo export PYTHONPATH=`pwd`

clean:
	@rm -vf *.pyc */*.pyc mailpile-tmp.py scripts/breeder.py mailpile.py
	@rm -vf .appver MANIFEST setup.cfg .SELF
	@rm -vrf *.egg-info build/ mp-virtualenv/ dist/
	@rm -vf debian/files debian/control debian/copyright debian/changelog
	@rm -vrf debian/pagekite* debian/python* debian/init.d

virtualenv:
	virtualenv mp-virtualenv
	bash -c 'source mp-virtualenv/bin/activate && pip install -r requirements.txt && python setup.py install'
	
