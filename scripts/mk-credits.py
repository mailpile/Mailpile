#!/usr/bin/python
import os
import re
import subprocess

os.chdir(os.path.join(os.path.dirname(__file__), '..'))

EMAIL_MAPPER = {
    '<smari@immi.is>': ('Smari McCarthy', '<smari@mailpile.is>'),
    '<smari@mailpile.is>': ('Smari McCarthy', '<smari@mailpile.is>'),
    '<git@pagekite.net>': ('Bjarni R. Einarsson', '<bre@mailpile.is>'),
    '<bre@klaki.net>': ('Bjarni R. Einarsson', '<bre@mailpile.is>'),
    '<hi@brennannovak.com>': ('Brennan Novak', '<bnvk@mailpile.is>'),
    '<hi@bnvk.me>': ('Brennan Novak', '<bnvk@mailpile.is>'),
    '<alexandre@alexandreviau.net>': ('Alexandre Viau', '<alexandre@alexandreviau.net>'),
}

authors = {}
translators = {}

# Get coders from git log
git_log = subprocess.Popen(['git', 'log'], stdout=subprocess.PIPE)
for line in git_log.stdout:
    if line.startswith('Author: '):
        author, email = line[8:].strip().rsplit(' ', 1)
        author, email = EMAIL_MAPPER.get(email, (author, email))
        if email.endswith('@mailpile.is>'):
            continue
        info = authors.get(email, [author, 0])
        info[1] += 1
        authors[email] = info
git_log.wait()
authors = [(c, n, e) for e, (n, c) in authors.iteritems()]

# Get translators from .po files
for lang in os.listdir('shared-data/locale'):
    po = 'shared-data/locale/%s/LC_MESSAGES/mailpile.po' % lang
    tr = translators[lang] = ['', []]
    try:
        with open(po, 'r') as fd:
            for line in fd:
                if not line.strip():
                    break    
                elif line.startswith('#') and '@' in line:
                    name = line[2:].strip()
                    if name not in tr[1]:
                        tr[1].append(name)
                elif line.startswith('"Language-Team: '):
                    tr[0] = line.split(': ')[1].split(' (')[0]   
    except:
        pass

code = 'shared-data/default-theme/html/page/release-notes/credits-code.html'
i18n = 'shared-data/default-theme/html/page/release-notes/credits-i18n.html'
with open(code, 'w') as fd:
    authors.sort(key=lambda a: a[1])
    fd.write('\n'.join('<li class="commits-%s">%s</li>' % (a[0], a[1])
                       for a in authors))

with open(i18n, 'w') as fd:
    email = re.compile(r'\s+<[^>]+>')
    for lang in sorted(translators.keys()):
        language, tlist = translators[lang]
        if language:
            fd.write('<li class="language">%s</li>\n' % language)
            fd.write(''.join('<li>%s</li>\n' % re.sub(email, '', n)
                             for n in sorted(tlist)))
        elif translators[lang][1]:
            print 'wtf: %s' % translators[lang]

os.system('ls -l %s %s' % (code, i18n))
