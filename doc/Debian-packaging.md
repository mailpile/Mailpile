### Debian packaging is considered experimental!

### Generating DEB packages ###

You first need to generate a changelog.
The following command uses an empty changelog message,
this will probably be changed in the future.

```bash
scripts/create-debian-changelog.py #May take some time
debuild -us -uc -b
```

The first command generates changelog messages for all git commit messages.
If you're not interested in a proper changelog, you can use this command
instead of *create-debian-changelog.py* to create an empty changelog:

```bash
dch --create -v 0.0.0-dev$(git rev-list $(git rev-parse HEAD) | wc -l)  --package mailpile ""
debuild -us -uc -b
```