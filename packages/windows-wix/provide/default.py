import build
import importlib
import glob
import os.path
import logging

logger = logging.getLogger(__name__)

build = build.Build()

script_dir = os.path.join(os.path.dirname(__file__), 'scripts')

for script_path in glob.iglob(os.path.join(script_dir, '*.py')):
    script_name = 'scripts.' + os.path.basename(script_path).split('.')[0]
    if script_name.endswith('__'):
        continue
    logger.debug("adding script: '{}'".format(script_name))
    script = importlib.import_module(script_name)
    script.bind(build)
