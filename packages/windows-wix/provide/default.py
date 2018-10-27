import build
import importlib
import glob
import os.path
import logging

logger = logging.getLogger(__name__)

build = build.Build()


# Detect/handle being invoked with '-m'
#
module_root = __name__.split('.')[:-1]
import_module = '.'.join(module_root)

if import_module:
    def import_file(name):
        '''
        When invoked with '-m', perform a relative import.
        '''
        return importlib.import_module('.' + name, import_module)
else:
    def import_file(name):
        '''
        When invoked without '-m', perform an absolute import.
        '''
        return importlib.import_module(name)

script_dir = os.path.join(os.path.dirname(__file__), 'scripts')

for script_path in glob.iglob(os.path.join(script_dir, '*.py')):
    script_name = 'scripts.' + os.path.basename(script_path).split('.')[0]
    if script_name.endswith('__'):
        continue
    logger.debug("adding script: '{}'".format(script_name))
    script = import_file(script_name)
    script.bind(build)
