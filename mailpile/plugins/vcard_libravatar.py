#coding:utf-8
import random
import time
from urllib2 import urlopen

import mailpile.util
from mailpile.conn_brokers import Master as ConnBroker
from mailpile.i18n import gettext as _
from mailpile.plugins import PluginManager
from mailpile.vcard import VCardImporter, MailpileVCard, VCardLine


_plugins = PluginManager(builtin=__file__)


class LibravatarImporter(VCardImporter):
    """
    This importer will pull contact details down from a central server,
    using the Libravatar JSON API and caching thumbnail data locally.

    For details, see https://wiki.libravatar.org/api/

    The importer will only pull down a few contacts at a time, to limit
    the impact on Libravatar's servers and prevent network traffic from
    stalling the rescan process too much.
    """
    FORMAT_NAME = 'Libravatar'
    FORMAT_DESCRIPTION = _('Import contact info from a Libravatar server')
    SHORT_NAME = 'libravatar'
    CONFIG_RULES = {
        'active': [_('Enable this importer'), bool, True],
        'anonymous': [_('Require anonymity for use'), bool, True],
        'interval': [_('Minimum days between refreshing'), 'int', 7],
        'batch': [_('Max batch size per update'), 'int', 30],
        'default': [_('Default thumbnail style'), str, 'retro'],
        'rating': [_('Preferred thumbnail rating'),
                   ['g', 'pg', 'r', 'x'], 'g'],
        'size': [_('Preferred thumbnail size'), 'int', 80],
        'url': [_('Libravatar server URL'), 'url', 'https://cdn.libravatar.com'],
    }
    VCARD_TS = 'x-libravatar-ts'
    VCARD_IMG = ''

    def _want_update(self):
        def _jittery_time():
            # This introduces 5 hours of jitter into the time check
            # below, biased towards extending the delay by an average
            # of 1.5 hours each time. This is mostly done to spread
            # out the load on the Libravatar server over time, as to
            # begin with all contacts will be checked at roughly the
            # same time.
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
        conn_need, conn_reject = [ConnBroker.OUTGOING_HTTP], []
        if self.config.anonymous:
            conn_reject += [ConnBroker.OUTGOING_TRACKABLE]
        with ConnBroker.context(need=conn_need, reject=conn_reject):
            self.session.ui.mark('Getting: %s' % url)
            return urlopen(url, data=None, timeout=3).read()

    def check_libravatar(self, vcard, email):
        img = vcf = json = None
        for vcl in vcard.get_all('email'):
            digest = mailpile.util.md5_hex(vcl.value.lower())
            try:
                if mailpile.util.QUITTING:
                    return None, None, None, None
                if not img:
                    img = self._get(('%s/avatar/%s?s=%s&r=%s&d=404'
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
                img = self._get(('%s/avatar/%s?s=%s&d=%s'
                                 ) % (self.config.url,
                                      mailpile.util.md5_hex(email.lower()),
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
            email, img, gcard, gjson = self.check_libravatar(contact, email)

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


_plugins.register_vcard_importers(LibravatarImporter)
