import cStringIO
import datetime
import gzip
import json
import os
import sys
import time
import traceback
import urllib
import zipfile

from mailpile.auth import VerifyAndStorePassphrase
from mailpile.config.defaults import APPVER
from mailpile.commands import Command
from mailpile.crypto.streamer import EncryptingStreamer, DecryptingStreamer
from mailpile.plugins import PluginManager
from mailpile.plugins.core import Quit
from mailpile.i18n import ActivateTranslation
from mailpile.i18n import gettext as _
from mailpile.i18n import ngettext as _n
from mailpile.ui import SuppressHtmlOutput
from mailpile.util import *
from mailpile.vfs import FilePath, vfs


_ = lambda t: t
_plugins = PluginManager(builtin=__file__)


def _gzip(filename, data):
    gzip_data = cStringIO.StringIO()
    gzip_obj = gzip.GzipFile(filename, 'w', 9, gzip_data, 0)
    gzip_obj.write(data)
    gzip_obj.close()
    return gzip_data.getvalue()


def _gunzip(data):
    with gzip.GzipFile('', 'rb', 0, cStringIO.StringIO(data)) as gzf:
        return gzf.read()


def _decrypt(data, config):
    with DecryptingStreamer(cStringIO.StringIO(data),
                            mep_key=config.get_master_key()) as fd:
        data = fd.read()
        fd.verify(_raise=IOError)
    return data


class MakeBackup(Command):
    """Generate an encrypted backup of Stuff"""
    SYNOPSIS = (None, 'backup', 'backup', '[download]')
    ORDER = ('Internals', 6)
    RAISES = (SuppressHtmlOutput,)
    CONFIG_REQUIRED = True
    IS_USER_ACTIVITY = False

    @classmethod
    def SummarizeTags(cls, config):
        # First, decide which tags to include.
        # Not all tags are interesting! Most, but not all.
        keep = {}
        suppress = {}
        for tid, tag in config.tags.iteritems():
            if tag.type in ('tag', 'group', 'attribute', 'inbox', 'drafts',
                            'sent', 'spam', 'read', 'tagged', 'fwded',
                            'replied', 'search', 'profile'):
                if tid in config.index.TAGS:
                    keep[tid] = tag
            elif tag.type == 'trash':
                suppress[tid] = tag

        msg_idx_set = set()
        for tid in keep:
            msg_idx_set |= config.index.TAGS[tid]
        for tid in suppress:
            msg_idx_set -= config.index.TAGS.get(tid, set([]))

        msg_id_list = [''] * len(config.index.INDEX)
        for msgid, msg_idx in config.index.MSGIDS.iteritems():
            if msg_idx in msg_idx_set:
                msg_id_list[msg_idx] = msgid

        return {
            'tags': dict((tid, list(config.index.TAGS[tid]))
                         for tid in keep),
            'msgids': msg_id_list}

    @classmethod
    def MakeBackupArchive(cls, config, gnupg, what=None):
        backup_date = datetime.date.today().strftime('%Y-%m-%d')
        if what:
            backup_fn = 'Mailpile_Backup_%s_%s.zip' % (
                backup_date, ','.join(what))
        else:
            backup_fn = 'Mailpile_Backup_%s.zip' % (backup_date,)

        # Prep archive!
        backup_data = cStringIO.StringIO()
        backup_zip = zipfile.ZipFile(backup_data, 'w', zipfile.ZIP_DEFLATED)
        backup_zip.writestr('README.txt', (('\n'.join([
            _("This is a backup of Mailpile v%(ver)s keys and configuration."),
            '',
            '   * ' + _("This backup was generated on: %(date)s."),
            '   * ' + _("The contents of this file should be encrypted."),
            '   * ' + _("The entire ZIP file must be uploaded during "
                        "restoration."),
            '',
            '-- ',
            '{"backup_date": "%(date)s",',
            ' "backup_version": 1.0,',
            ' "mailpile_version": "%(ver)s"}'
            ])) % {'ver': APPVER, 'date': backup_date}).strip())
        backup_contents = []

        def _add_file(realfile, zipname):
            backup_zip.write(realfile, zipname)
            backup_contents.append(zipname)

        # The .ZIP is unencrypted, so generated contents needs protecting
        def _encrypt_and_add_data(filename, data):
            tempfile = os.path.join(config.tempfile_dir(), filename)
            with EncryptingStreamer(config.get_master_key(),
                                    dir=config.tempfile_dir()) as fd:
                fd.write(data)
                fd.save(tempfile)
            _add_file(tempfile, filename)
            safe_remove(tempfile)

        # What has been requested?
        if what and what[0] == 'full':
            what += ['config', 'profiles', 'keys', 'gnupg', 'vcards', 'tags']

        # Critical: Copy the configuration and master keys
        if not what or 'config' in what:
            for fn in (config.conf_pub, config.conf_key, config.conffile):
                _add_file(fn, os.path.basename(fn))

        # Critical: Copy the profile VCard data
        if not what or 'profiles' in what:
            for profile in config.vcards.find_vcards([], kinds=['profile']):
                target = os.path.basename(profile.filename)
                _add_file(profile.filename, os.path.join('vcards', target))

        # Critical: Copy all the private GnuPG keys!
        if not what or 'keys' in what:
            _encrypt_and_add_data('gnupg-privkeys.asc.gze',
                _gzip('gnupg-privkeys.asc', gnupg.export_privkeys()))

        # Recommended: Copy all the public GnuPG keys!
        if not what or 'gnupg' in what:
            _encrypt_and_add_data('gnupg-pubkeys.asc.gze',
                _gzip('gnupg-pubkeys.asc', gnupg.export_pubkeys()))

        # Recommended: Copy the "interesting" VCards.
        if not what or 'vcards' in what:
            for vcard in config.vcards.find_vcards([],
                    kinds=['individual', 'group']):
                if ((what and 'full' in what)
                        or vcard.recent_history()
                        or vcard.crypto_policy
                        or vcard.html_policy
                        or vcard.pgp_key_shared
                        or vcard.pgp_key):
                    target = os.path.basename(vcard.filename)
                    _add_file(vcard.filename, os.path.join('vcards', target))

        # Optional: Backup the tag structure. This is useful if we lose the
        # metadata index, but have the original e-mails. This is DISABLED BY
        # DEFAULT because it is expensive and that may not be a real use case.
        if what and 'tags' in what:
            _encrypt_and_add_data('tags.json.gze',
                _gzip('tags.json', json.dumps(cls.SummarizeTags(config))))

        # Finalize archive
        backup_zip.close()
        backup_data = backup_data.getvalue()

        return backup_fn, backup_contents, backup_data

    def command(self):
        session, config = self.session, self.session.config
        html_variables = session.ui.html_variables

        if not (html_variables and
                session.ui.valid_csrf_token(self.data.get('csrf', [''])[0])):
            raise AccessError('Invalid CSRF token')

        backup_fn, backup_contents, backup_data = self.MakeBackupArchive(
            config, self._gnupg(),
            what=[a for a in self.args if a not in ('download',)])

        if 'download' in self.args:
            encoded_fn = urllib.quote(backup_fn.encode('utf-8'))
            request = html_variables['http_request']
            request.send_http_response(200, 'OK')
            request.send_standard_headers(mimetype='application/zip',
                                          header_list=[
                ('Content-Length', len(backup_data)),
                ('Content-Disposition',
                    'attachment; filename*=UTF-8\'\'%s' % (encoded_fn,))])
            request.wfile.write(backup_data)
            raise SuppressHtmlOutput()

        return self._success('Generated backup', result={
            'filename': backup_fn,
            'contents': backup_contents,
            'data_b64': backup_data.encode('base64')})


AVAILABLE_BACKUPS = {}

class RestoreBackup(Command):
    """Bootstraup setup from a backup archive"""
    SYNOPSIS = (None, 'backup/restore', 'backup/restore', '[/path/to.zip]')
    ORDER = ('Internals', 6)
    RAISES = (UrlRedirectException,)
    CONFIG_REQUIRED = False
    HTTP_AUTH_REQUIRED = 'maybe'
    HTTP_CALLABLE = ('GET', 'POST')
    HTTP_QUERY_VARS = {
        'lang': 'Language to use in UI'}
    HTTP_POST_VARS = {
        'restore': 'date of backup to restore',
        'password': 'Mailpile master password',
        'keychain': 'GnuPG keychain policy: shared*, mailpile, none',
        'os_settings': 'OS settings policy: keep, backup*',
        'file-data': 'file data'}

    def _restore_PGP_keys(self, config, backup_zip, policy):
        if policy not in ('shared', 'mailpile'):
            return

        if policy == 'mailpile':
            config.sys.gpg_home = config.workdir
        else:
            config.sys.gpg_home = ''

        for keyfile in ('gnupg-pubkeys.asc.gze', 'gnupg-privkeys.asc.gze'):
            gze = backup_zip.read(keyfile)
            print 'DATA: %s' % gze
            self._gnupg().import_keys(_gunzip(_decrypt(gze, config)))


    def _adjust_paths(self, config):
        # Go through sys.mailboxes, sources.*.mailbox:
        #   - if the path is outside Workdir, does not exist, clear entry
        #   - if the path is inside Workdir, does not exist, create it
        #   - if the path is src:, source does not exist, clear entry
        def path_ok(mbx_path):
            if 'src:' in mbx_path.raw_fp[:5]:
                return True
            elif vfs.mailbox_type(mbx_path, config):
                return True
            elif unicode(mbx_path).startswith('/Mailpile$/'):
                config.create_local_mailstore(
                    self.session, name=mbx_path.raw_fp)
                return True
            else:
                return False

        for i, mbx_path in config.sys.mailbox.iteritems():
            mbx_path = FilePath(mbx_path)
            if not path_ok(mbx_path):
                config.sys.mailbox[i] = '/dev/null'

        for i, p, src in config.get_mailboxes(with_mail_source=True,
                                              mail_source_locals=True):
            mbx_path = FilePath(p)
            if src.mailbox[i].local and not path_ok(mbx_path):
                src.mailbox[i].local = '!CREATE'

    def command(self):
        global AVAILABLE_BACKUPS
        session, config = self.session, self.session.config
        message, results = '', {}

        if config.prefs.gpg_recipient or os.path.exists(config.conf_key):
            raise UrlRedirectException('/' + (config.sys.http_path or ''))

        if 'lang' in self.data:
            ActivateTranslation(session, config, self.data['lang'][0])

        password = ''
        if self.args and '_method' not in self.data:
            try:
                if self.args[0] in AVAILABLE_BACKUPS:
                    backup_data = AVAILABLE_BACKUPS[self.args[0]]
                    self.data['restore'] = [self.args[0]]
                    password = session.ui.get_password(_("Your password: "))
                else:
                    with open(self.args[0], 'r') as fd:
                        backup_data = fd.read()
            except (IOError, OSError):
                return self._error('Failed to read: %s' % self.args[0])
        elif self.data.get('_method') == 'POST':
            if 'restore' in self.data:
                backup_data = AVAILABLE_BACKUPS[self.data['restore'][0]]
                password = self.data.get('password', [''])[0]
            else:
                backup_data = self.data.get('file-data', [None])[0]
        else:
            backup_data = None

        if backup_data is not None:
            try:
                if isinstance(backup_data, str):
                    backup_data = cStringIO.StringIO(backup_data)
                backup_zip = zipfile.ZipFile(backup_data, 'r')

                # Load and validate metadata (from README.txt)
                results['metadata'] = metadata = json.loads(
                    backup_zip.read('README.txt').split('-- ')[1])
                results['metadata']['contents'] = backup_zip.namelist()
                backup_date = metadata['backup_date']
                if metadata['backup_version'] != 1.0:
                    raise ValueError('Unrecognized backup version')

                # If we get this far, the backup looks good. Restore?
                if (password and
                        backup_date == self.data.get('restore', [''])[0]):
                    # This should be safe: we are in the setup phase where
                    # almost no background stuff is running, so it should be
                    # fine to just overwrite files and reload.
                    config.stop_workers()
                    backup_zip.extractall(config.workdir)
                    VerifyAndStorePassphrase(config, password)

                    os_gpg_home = config.sys.gpg_home
                    os_gpg_binary = config.sys.gpg_binary
                    os_http_port = config.sys.http_port
                    os_minfree_mb = config.sys.minfree_mb
                    try:
                        config.load(session)
                    except IOError:
                        pass

                    B = ['backup']
                    if 'keep' == self.data.get('os_settings', B)[0]:
                        config.sys.gpg_home = os_gpg_home
                        config.sys.gpg_binary = os_gpg_binary
                        config.sys.http_port = os_http_port
                        config.sys.minfree_mb = os_minfree_mb

                    self._restore_PGP_keys(config, backup_zip,
                        self.data.get('keychain', ['shared'])[0])

                    self._adjust_paths(config)

                    config.prepare_workers(session, daemons=True)
                    message = _('Backup restored')
                    results['restored'] = True
                    AVAILABLE_BACKUPS = {}
                else:
                    message = _('Backup validated, restoration is possible')
                    AVAILABLE_BACKUPS[backup_date] = backup_data

            except (ValueError, KeyError, zipfile.BadZipfile, IOError):
                traceback.print_exc()
                return self._error('Incomplete, invalid or corrupt backup')
        else:
            message = _('Restore from backup')

        results['available'] = AVAILABLE_BACKUPS.keys()
        return self._success(message, result=results)


_plugins.register_commands(MakeBackup, RestoreBackup)
