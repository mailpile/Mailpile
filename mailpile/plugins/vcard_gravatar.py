#coding:utf-8
import os
import random
import time
from gettext import gettext as _
from urllib2 import urlopen

import mailpile.util
from mailpile.plugins import PluginManager
from mailpile.util import *
from mailpile.vcard import *


_plugins = PluginManager(builtin=__file__)


class GravatarImporter(VCardImporter):
    """
    This importer will pull contact details down from a central server,
    using the Gravatar JSON API and caching thumbnail data locally.

    For details, see https://secure.gravatar.com/site/implement/

    The importer will only pull down a few contacts at a time, to limit
    the impact on Gravatar's servers and prevent network traffic from
    stalling the rescan process too much.
    """
    FORMAT_NAME = 'Gravatar'
    FORMAT_DESCRIPTION = _('Import contact info from a Gravatar server')
    SHORT_NAME = 'gravatar'
    CONFIG_RULES = {
        'active': [_('Enable this importer'), bool, True],
        'interval': [_('Minimum days between refreshing'), 'int', 7],
        'batch': [_('Max batch size per update'), 'int', 30],
        'default': [_('Default thumbnail style'), str, 'retro'],
        'rating': [_('Preferred thumbnail rating'),
                   ['g', 'pg', 'r', 'x'], 'g'],
        'size': [_('Preferred thumbnail size'), 'int', 80],
        'url': [_('Gravatar server URL'), 'url', 'https://en.gravatar.com'],
    }
    VCARD_TS = 'x-gravatar-ts'
    VCARD_IMG = ''

    def _want_update(self):
        def _jittery_time():
            # This introduces 5 hours of jitter into the time check below,
            # biased towards extending the delay by an average of 1.5 hours
            # each time. This is mostly done to spread out the load on the
            # Gravatar server over time, as to begin with all contacts will
            # be checked at roughly the same time.
            return time.time() + random.randrange(-14400, 3600)

        want = []
        vcards = self.session.config.vcards
        for vcard in vcards.find_vcards([]):
            try:
                ts = int(vcard.get(self.VCARD_TS).value)
            except IndexError:
                ts = 0
            if ts < _jittery_time() - (self.config.interval * 24 * 3600):
                want.append(vcard)
            if len(want) >= self.config.batch:
                break
        return want

    def get_vcards(self):
        if not self.config.active:
            return []

        def _b64(data):
            return data.encode('base64').replace('\n', '')

        def _get(url):
            self.session.ui.mark('Getting: %s' % url)
            return urlopen(url, data=None, timeout=3).read()

        results = []
        for contact in self._want_update():
            if mailpile.util.QUITTING:
                return []

            vcls = [VCardLine(name=self.VCARD_TS, value=int(time.time()))]
            email = contact.email
            if not email:
                continue

            img = json = None
            for vcl in contact.get_all('email'):
                digest = md5_hex(vcl.value.lower())
                try:
                    if mailpile.util.QUITTING:
                        return []
                    if not img:
                        img = _get(('%s/avatar/%s.jpg?s=%s&r=%s&d=404'
                                    ) % (self.config.url,
                                         digest,
                                         self.config.size,
                                         self.config.rating))
                    if not json:
                        json = _get('%s/%s.json' % (self.config.url, digest))
                        email = vcl.value
                except IOError:
                    pass

            if json:
                pass  # FIXME: parse the JSON

            if (self.config.default != '404') and not img:
                try:
                    img = _get(('%s/avatar/%s.jpg?s=%s&d=%s'
                                ) % (self.config.url,
                                     md5_hex(email.lower()),
                                     self.config.size,
                                     self.config.default))
                except IOError:
                    pass

            if img:
                vcls.append(VCardLine(
                    name='photo',
                    value='data:image/jpeg;base64,%s' % _b64(img),
                    mediatype='image/jpeg'
                ))

            vcls.append(VCardLine(name='email', value=email))
            results.append(SimpleVCard(*vcls))
        return results


_plugins.register_vcard_importers(GravatarImporter)
