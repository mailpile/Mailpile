import json
import os
import sys
import threading
import time
import traceback
import urllib
import webbrowser


class Indicator(object):
    def __init__(self, config):
        self.config = config
        self.ready = False

    def _do(self, method, action):
        method = method.lower()

        if method == 'show':
            webbrowser.open(action)

        elif method in ('get', 'post'):
            uo = urllib.URLopener()
            uo.addheader('Cookie', '%s=%s' % (self.config['cookie'],
                                              self.config['session_id']))
            if method == 'post':
                url, data = action.split('?', 1)
                (fn, hdrs) = uo.retrieve(url, data=data)
            else:
                (fn, hdrs) = uo.retrieve(action)
            hdrs = unicode(hdrs)
            with open(fn, 'rb') as fd:
                data = fd.read().strip()
            if data.startswith('{') and 'application/json' in hdrs:
                data = json.loads(data)
                if 'message' in data:
                    self.notify_user(data['message'])
            print '%s' % data

    def notify_user(self, message):
        print 'NOTIFY: %s' % message

    def set_status_startup(self):
        pass

    def set_status_normal(self):
        pass

    def set_status_working(self):
        pass

    def set_status_attention(self):
        pass

    def set_menu_name(self, item=None, name=None):
        pass

    def set_menu_sensitive(self, item=None, sensitive=True):
        pass


def UnityIndicator():
    import gobject
    import gtk
    import appindicator
    try:
        import pynotify
        pynotify.init("Mailpile")
    except ImportError:
        pynotify = None

    gobject.threads_init()

    class MailpileIndicator(Indicator):
        def _menu_setup(self):
            self.menu = gtk.Menu()
            self.items = {}
            for text, method, action in self.config.get('menu', []):
                item = gtk.MenuItem(text)
                item.set_sensitive(False)
                if method:
                    def activate(m, a):
                        return lambda d: self._do(m, a)
                    item.connect("activate", activate(method, action))
                item.show()
                self.items[text] = item
                self.menu.append(item)

        def _ind_setup(self):
            self.ind = appindicator.Indicator(
                "mailpile-indicator", "indicator-messages",
                appindicator.CATEGORY_COMMUNICATIONS)
            self.ind.set_icon(
                os.path.join(os.path.dirname(os.path.realpath(__file__)),
                             'mailpile.png'))
            self.ind.set_status(appindicator.STATUS_ATTENTION)
            self.ind.set_attention_icon("new-messages-red")
            self.ind.set_menu(self.menu)
            self.set_status_startup()

        def notify_user(self, message):
            if pynotify:
                notification = pynotify.Notification(
                    "Mailpile", message, "dialog-warning")
                notification.set_urgency(pynotify.URGENCY_NORMAL)
                notification.show()
            else:
                print 'FIXME: Notify: %s' % message

        def set_status_startup(self):
            gobject.idle_add(self.ind.set_status,
                             appindicator.STATUS_ACTIVE)

        def set_status_normal(self):
            gobject.idle_add(self.ind.set_status,
                             appindicator.STATUS_ACTIVE)

        def set_status_working(self):
            gobject.idle_add(self.ind.set_status,
                             appindicator.STATUS_ACTIVE)

        def set_status_attention(self):
            gobject.idle_add(self.ind.set_status,
                             appindicator.STATUS_ATTENTION)

        def set_menu_name(self, item=None, name=None):
            if item and item in self.items:
                gobject.idle_add(self.items[item].set_label, name)

        def set_menu_sensitive(self, item=None, sensitive=True):
            if item and item in self.items:
                gobject.idle_add(self.items[item].set_sensitive, sensitive)

        def run(self):
            self._menu_setup()
            self._ind_setup()
            self.ready = True
            try:
                gtk.main()
            except:
                traceback.print_exc()

    return MailpileIndicator


def MacOSXIndicator():
    return None


def WxWindowsIndicator():
    return None


class StdinWatcher(threading.Thread):
    def __init__(self, config, gui_object):
        threading.Thread.__init__(self)
        self.daemon = True
        self.config = config
        self.gui = gui_object

    def do(self, command, kwargs):
        if hasattr(self.gui, command):
            getattr(self.gui, command)(**kwargs)
        else:
            print 'Unknown method: %s' % command

    def run(self):
        try:
            while not self.gui.ready:
                time.sleep(0.1)
            while True:
                line = sys.stdin.readline()
                if not line:
                    break
                try:
                    cmd, args = line.split(' ', 1)
                    self.do(cmd, json.loads(args))
                except (ValueError, IndexError, NameError):
                    traceback.print_exc()
        except:
            traceback.print_exc()
        finally:
            os._exit(0)


if __name__ == '__main__':
    indicator, config = None, []

    while True:
        line = sys.stdin.readline()
        if not line or line.strip() == 'OK GO':
            break
        config.append(line)
    config = json.loads(''.join(config))

    for cls in (MacOSXIndicator,
                UnityIndicator,
                WxWindowsIndicator):
        indicator = cls()
        if indicator:
            indi = indicator(config)
            StdinWatcher(config, indi).start()
            indi.run()
            break
