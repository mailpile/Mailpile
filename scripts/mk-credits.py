#!/usr/bin/python
import os
import subprocess

EMAIL_MAPPER = {
    '<smari@immi.is>': ('Smari McCarthy', '<smari@mailpile.is>'),
    '<smari@mailpile.is>': ('Smari McCarthy', '<smari@mailpile.is>'),
    '<git@pagekite.net>': ('Bjarni R. Einarsson', '<bre@mailpile.is>'),
    '<bre@klaki.net>': ('Bjarni R. Einarsson', '<bre@mailpile.is>'),
    '<hi@brennannovak.com>': ('Brennan Novak', '<bnvk@mailpile.is>'),
    '<hi@bnvk.me>': ('Brennan Novak', '<bnvk@mailpile.is>'),
}

authors = {}
translators = {}

# Get coders from git log
git_log = subprocess.Popen(['git', 'log'], stdout=subprocess.PIPE)
for line in git_log.stdout:
    if line.startswith('Author: '):
        author, email = line[8:].strip().rsplit(' ', 1)
        author, email = EMAIL_MAPPER.get(email, (author, email))
        info = authors.get(email, [author, 0])
        info[1] += 1
        authors[email] = info
git_log.wait()
authors = reversed(sorted([(c, n, e) for e, (n, c) in authors.iteritems()]))

# Get translators from .po files
for lang in os.listdir('mailpile/locale'):
    po = 'mailpile/locale/%s/LC_MESSAGES/mailpile.po' % lang
    tr = translators[lang] = ['', []]
    try:
        with open(po, 'r') as fd:
            for line in fd:
                if not line.strip():
                    break    
                elif line.startswith('#') and '@' in line:
                    tr[1].append(line[2:].strip())
                elif line.startswith('"Language-Team: '):
                    tr[0] = line.split(': ')[1].split(' (')[0]   
    except:
        pass

print '%s' % '\n'.join('%s' % (a,) for a in authors)
print '%s' % translators
