import time
import warnings

from mailpile.i18n import gettext as _
from mailpile.mailutils.safe import safe_decode_hdr
from mailpile.plugins import PluginManager
from mailpile.vcard import MailpileVCard, VCardImporter, VCardLine


_plugins = PluginManager(builtin=__file__)


class FaceImporter(VCardImporter):
    """
    Get avatar from Face header.
    """
    HOOKS = ['META_KW_EXTRACTORS']
    FORMAT_NAME = 'Face'
    FORMAT_DESCRIPTION = _('Get avatar from Face header.')
    SHORT_NAME = 'face'
    CONFIG_RULES = {
        'active': [_('Enable this importer'), bool, True],
    }
    VCARD_TS = 'x-face-ts'
    VCARD_IMG = ''

    def __init__(self):
        pass

    def __call__(
            self, mail_idx, msg_mid, message, msg_size, msg_ts,
            session=None, **kwargs):
        email = safe_decode_hdr(msg=message, name='from')
        configs = session.config.prefs.vcard.importers[self.SHORT_NAME]

        # Add face vcard.
        face = safe_decode_hdr(msg=message, name='face')
        if face:
            if len(face) > 998:
                warnings.warn(
                    email + "'s face header exceeds the maximum size. "
                    "See the spec: http://quimby.gnus.org/circus/face/")
                return []

            vcard = MailpileVCard(
                VCardLine(name=self.VCARD_TS, value=int(time.time())),
                VCardLine(
                    name='photo',
                    value='data:image/png;base64,%s' % face,
                    media_type='image/png'),
                VCardLine(name='email', value=email))

            for config in configs:
                if config:
                    self.config = config
                    self.merge_or_create_vcard(session, session.config.vcards, vcard)

        # Return no keywords.
        return []


_plugins.register_vcard_importers(FaceImporter())
