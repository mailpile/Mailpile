import time

from mailpile.i18n import gettext as _
from mailpile.mailutils import Email
from mailpile.plugins import PluginManager
from mailpile.search import MailIndex
from mailpile.vcard import MailpileVCard, VCardImporter, VCardLine


_plugins = PluginManager(builtin=__file__)


class FaceImporter(VCardImporter):
    """
    Get avatar from Face header.
    """
    FORMAT_NAME = 'Face'
    FORMAT_DESCRIPTION = _('Get avatar from Face header.')
    SHORT_NAME = 'face'
    CONFIG_RULES = {
        'active': [_('Enable this importer'), bool, True],
    }
    VCARD_TS = 'x-face-ts'
    VCARD_IMG = ''

    def get_vcards(self):
        mail_index = MailIndex(self.session.config)
        mail_index.load(self.session)
        results = []

        for vcard in self.session.config.vcards.values():
            # Get latest message from vcard email address.
            from_messages = list(mail_index.search(
                self.session, ['from:' + vcard.email]).as_set())
            if not from_messages:
                continue
            mail_index.sort_results(self.session, from_messages, 'date')
            latest_message = Email(mail_index, from_messages.pop()).get_msg()

            # Add face vcard.
            face = mail_index.hdr(latest_message, 'face')
            if face:
                results.append(self._make_vcard(vcard.email, VCardLine(
                    name='photo',
                    value='data:image/png;base64,%s' % face,
                    media_type='image/png')))

        return results

    def _make_vcard(self, email, face_line):
        return MailpileVCard(
            VCardLine(name=self.VCARD_TS, value=int(time.time())),
            face_line,
            VCardLine(name='email', value=email))


_plugins.register_vcard_importers(FaceImporter)
