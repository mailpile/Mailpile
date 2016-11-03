import sys
import time
import warnings

from mailpile.i18n import gettext as _
from mailpile.mailutils import Email
from mailpile.plugins import PluginManager
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
        mail_index = self.session.config.get_index(self.session)
        results = []

        for vcard in self.session.config.vcards.values():
            email = vcard.email

            # Get latest message from vcard email address.
            from_messages = list(mail_index.search(
                self.session, ['from:' + email]).as_set())
            if not from_messages:
                continue
            mail_index.sort_results(self.session, from_messages, 'date')
            latest_message = Email(mail_index, from_messages.pop()).get_msg()

            # Add face vcard.
            face = mail_index.hdr(latest_message, 'face')
            if face:
                if sys.getsizeof(face) > 998:
                    warnings.warn(
                        email + "'s face header exceeds the maximum size. "
                        "See the spec: http://quimby.gnus.org/circus/face/")
                    continue
                results.append(self._make_vcard(email, VCardLine(
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
