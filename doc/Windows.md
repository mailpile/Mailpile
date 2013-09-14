# Windows and Mailpile

Windows support is currently incomplete.

Download links used to resolve dependencies:

    python 2.7: <http://www.python.org/download/>
    lxml: <http://www.lfd.uci.edu/~gohlke/pythonlibs/#lxml>
    pyreadline: <https://pypi.python.org/pypi/pyreadline/2.0>

There is a windows-equivalent to "mp" in the root directory. This should
match the behavior of the existing "mp" assuming the user installed python
2.7 in the default installation location.

GnuPGInterface does NOT appear to be installable for windows architectures.
At some point this dependency will be removed and replaced with something
that is actually Windows compatible.

