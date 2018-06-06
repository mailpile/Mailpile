#!/usr/bin/python

'''
Helper for unpacking MSIs in various ways. Generic high-level API:

extract( msi_path, out_path, features = ALL )
'''

ALL = '***ALL***'

import subprocess
import logging
import tempfile
import shutil
import os.path
import os

logger = logging.getLogger(__name__)


class LessMSI(object):
    '''
    Use lessmsi to extract the msi. TODO: handle features
    '''

    def __init__(self, lessmsi_path):
        self.lessmsi = lessmsi_path

    def __call__(self, msi_path, out_path, features=ALL):
        logger.info('Extracting {} to {} (features:{}) with lessmsi'.format(
            msi_path, out_path, features))
        if features != ALL:
            logger.warning("LessMSI doesn't implement feature selection(yet)!")

        temp_dir = tempfile.mkdtemp()

        if not temp_dir.endswith('\\'):
            temp_dir += '\\'

        args = (self.lessmsi, 'x', msi_path, temp_dir)
        try:
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            subprocess.check_call(args, startupinfo=si)
            sub_dirs = os.listdir(temp_dir)
            if len(sub_dirs) == 1:
                src_dir = os.path.join(temp_dir, sub_dirs[0])
            else:
                logger.warning("Ambiguous MSI root dir {}".format(msi_path))
                src_dir = temp_dir

            if not os.path.exists(out_path):
                shutil.move(src_dir, out_path)
            else:
                raise OSError("Path '{}' already exists".format(out_path))
        finally:
            def log_error(func, path, exec_info):
                logger.error("Error cleaning up {}: {} {}".format(msi_path, func, path),
                             exec_info=exec_info)
            shutil.rmtree(temp_dir, ignore_errors=True, onerror=log_error)


def bind(build):

    @build.provide('extract_msi')
    def provide_extract_msi(build, keyword):
        lessmsi_dir = build.depend('lessmsi')
        lessmsi_path = os.path.join(build.depend('lessmsi'), 'lessmsi.exe')
        extractor = LessMSI(lessmsi_path)
        return extractor
