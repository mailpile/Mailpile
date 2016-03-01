#coding:utf-8
import os
import random
import time

import mailpile.util
from mailpile.i18n import gettext as _
from mailpile.i18n import ngettext as _n
from mailpile.plugins import PluginManager
from mailpile.security import secure_urlget
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
        'anonymous': [_('Require anonymity for use'), bool, True],
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
        for vcard in vcards.find_vcards([], kinds=vcards.KINDS_PEOPLE):
            try:
                ts = int(vcard.get(self.VCARD_TS).value)
            except IndexError:
                ts = 0
            if ts < _jittery_time() - (self.config.interval * 24 * 3600):
                want.append(vcard)
            if len(want) >= self.config.batch:
                break
        return want

    def _get(self, url):
        self.session.ui.mark('Getting: %s' % url)
        return secure_urlget(self.session, url,
                             timeout=5,
                             anonymous=self.config.anonymous)

    def check_gravatar(self, vcard, email):
        img = vcf = json = None
        for vcl in vcard.get_all('email'):
            digest = md5_hex(vcl.value.lower())
            try:
                if mailpile.util.QUITTING:
                    return None, None, None, None
                if not img:
                    img = self._get(('%s/avatar/%s.jpg?s=%s&r=%s&d=404'
                                     ) % (self.config.url,
                                          digest,
                                          self.config.size,
                                          self.config.rating))

                # FIXME
                #if not vcf:
                #    vcf = self._get('%s/%s.vcf' % (self.config.url, digest))

                # FIXME
                #if not json:
                #    json = self._get('%s/%s.json' % (self.config.url, digest))

                if img or vcf or json:
                    email = vcl.value
            except IOError:
                pass

        if (self.config.default != '404') and not img:
            try:
                img = self._get(('%s/avatar/%s.jpg?s=%s&d=%s'
                                 ) % (self.config.url,
                                      md5_hex(email.lower()),
                                      self.config.size,
                                      self.config.default))
            except IOError:
                pass

        return email, img, vcf, json

    def get_vcards(self):
        if not self.config.active:
            return []

        def _b64(data):
            return data.encode('base64').replace('\n', '')

        results = []
        for contact in self._want_update():
            email = contact.email
            if not email:
                continue

            if mailpile.util.QUITTING:
                return []

            vcard = MailpileVCard(VCardLine(name=self.VCARD_TS,
                                            value=int(time.time())))
            email, img, gcard, gjson = self.check_gravatar(contact, email)

            if gcard:
                # FIXME: Is this boring?
                # vcard.load(data=gcard)
                pass

            if gjson:
                # FIXME: This is less boring!
                pass

            if img:
                vcard.add(VCardLine(
                    name='photo',
                    value='data:image/jpeg;base64,%s' % _b64(img),
                    mediatype='image/jpeg'
                ))

            if gcard or gjson or img:
                vcard.add(VCardLine(name='email', value=email))
                results.append(vcard)
        return results


_plugins.register_vcard_importers(GravatarImporter)
