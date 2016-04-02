import os

from jinja2 import BaseLoader, TemplateNotFound


class MailpileJinjaLoader(BaseLoader):
    """
    A Jinja2 template loader which uses the Mailpile configuration
    and plugin system to find template files.
    """
    def __init__(self, config):
        self.config = config

    def get_template_path(self, tpl):
        return self.config.data_file_and_mimetype('html_theme', tpl)[0]

    def get_source(self, environment, template):
        tpl = os.path.join('html', template)

        path = self.get_template_path(tpl)
        if not path:
            raise TemplateNotFound(tpl)

        mtime = os.path.getmtime(path)
        unchanged = lambda: (
            path == self.get_template_path(tpl)
            and mtime == os.path.getmtime(path))

        with file(path) as f:
            source = f.read().decode('utf-8')

        return source, path, unchanged
