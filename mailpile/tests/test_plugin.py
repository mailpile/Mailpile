import shutil
import os
from os import path
from mailpile.tests import MailPileUnittest
import json


class PluginTest(MailPileUnittest):
    def setUp(self):
        plugins = os.path.join(self.config.workdir, 'plugins')
        shutil.rmtree(plugins, ignore_errors=True)
        os.mkdir(plugins)

        self.plugin_dir = plugins

    def tearDown(self):
        shutil.rmtree(self.plugin_dir)

    def test_plugin_is_discovered(self):
        self._create_manifest('some_plugin', self._create_manifest_json('some_plugin'))
        self.config.plugins.discover([self.plugin_dir])

        self.assertTrue('some_plugin' in self.config.plugins.available())

    def test_code_files_are_loaded_in_order(self):
        # given
        def create_python_file_add_stmt(number, filename):
            self._create_code_file('from mailpile.plugins.order import add\nadd(%d)' % number, path.join(order_plugin_path, filename))

        order_plugin_path = path.join(self.plugin_dir, 'order')
        os.mkdir(order_plugin_path)

        create_python_file_add_stmt(1, 'first.py')
        create_python_file_add_stmt(2, 'second.py')
        create_python_file_add_stmt(3, 'third.py')

        self._create_code_file('x = []\ndef add(value):\n\tx.append(value)\n', path.join(order_plugin_path, 'order.py'))

        manifest = self._create_manifest_json('order')
        manifest['code']['python'] = ['order.py', 'first.py', 'second.py', 'third.py']

        self._create_manifest('order', manifest)

        #when
        self.config.plugins.discover([self.plugin_dir])

        try:
            self.mp.plugins_load('order')
            from mailpile.plugins.order import x
            #then
            self.assertEqual([1, 2, 3], x)
        finally:
            self.mp.plugins_disable('order')

    def _create_manifest(self, name, json_data):
        order_plugin = os.path.join(self.plugin_dir, name)
        if not os.path.exists(order_plugin):
            os.mkdir(order_plugin)
        manifest_file = os.path.join(order_plugin, 'manifest.json')

        with open(manifest_file, 'w') as fp:
            json.dump(json_data, fp)

    def _create_manifest_json(self, name):
        doc = dict()
        doc['name'] = name
        doc['author'] = 'Some Author'
        doc['code'] = {
            'python': [],
            'javascript': [],
            'css': []
        }

        return doc

    def _create_code_file(self, content, filename):
        with open(filename, 'w') as fp:
            fp.write(content)
