#!/usr/bin/python2 -u
#
# This is a general-purpose GUI which can be configured and controlled
# using a very simple line-based (JSON) protocol.
#
import json
import os
import sys
import threading
import time
import traceback
import urllib
import webbrowser


##[ Parent Indicator class, interface and common helpers ]####################

class Indicator(object):
    def __init__(self, config):
        self.config = config
        self.ready = False

    def _do(self, op, args):
        op = op.lower()

        if op == 'show_url':
            webbrowser.open(args[0])

        elif op in ('get_url', 'post_url'):
            url = args.pop(0)
            base_url = '/'.join(url.split('/')[:3])

            uo = urllib.URLopener()
            for cookie, value in self.config.get('http_cookies', {}
                                                 ).get(base_url, []):
                uo.addheader('Cookie', '%s=%s' % (cookie, value))

            if op == 'post_url':
                (fn, hdrs) = uo.retrieve(url, data=args)
            else:
                (fn, hdrs) = uo.retrieve(url)
            hdrs = unicode(hdrs)

            with open(fn, 'rb') as fd:
                data = fd.read().strip()

            if data.startswith('{') and 'application/json' in hdrs:
                data = json.loads(data)
                if 'message' in data:
                    self.notify_user(data['message'])

    def _add_menu_item(self, item='item', label='Menu item', sensitive=False,
                             op=None, args=None, **ignored_kwargs):
        pass

    def _create_menu_from_config(self):
        for item_info in self.config.get('indicator_menu', []):
            self._add_menu_item(**item_info)

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

    def set_menu_label(self, item=None, label=None):
        pass

    def set_menu_sensitive(self, item=None, sensitive=True):
        pass


##[ An indicator for Ubuntu's Unity ]##########################################

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
            self.items = {}
            self.menu = gtk.Menu()
            self._create_menu_from_config()

        def _add_menu_item(self, item='item', label='Menu item',
                                 sensitive=False,
                                 op=None, args=None,
                                 **ignored_kwarg):
            menu_item = gtk.MenuItem(label)
            menu_item.set_sensitive(sensitive)
            if op:
                def activate(o, a):
                    return lambda d: self._do(o, a)
                menu_item.connect("activate", activate(op, args or []))
            menu_item.show()
            self.items[item] = menu_item
            self.menu.append(menu_item)

        def _ind_setup(self):
            self.ind = appindicator.Indicator(
                self.config.get('app_name', 'app').lower() + "-indicator",
                "indicator-messages",
                appindicator.CATEGORY_COMMUNICATIONS)
            if 'indicator_icon' in self.config:
                self.ind.set_icon(self.config['indicator_icon'])
            else:
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

        def set_menu_label(self, item=None, label=None):
            if item and item in self.items:
                gobject.idle_add(self.items[item].set_label, label)

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


##[ An indicator for Mac OS X ]###############################################

try:
    import objc
    from Foundation import *
    from AppKit import *
    from PyObjCTools import AppHelpler
except ImportError:
    objc = None


def MacOSXIndicator():
    assert(objc is not None)

    class MailpileIndicator(Indicator):
        def _menu_setup(self):
            statusbar = NSStatusBar.systemStatusBar()
            statusitem = statusbar.statusItemWithLength_(
                NSSquareStatusItemLength)
            statusitem.setImage_()
            statusitem.setMenu_()

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

        def set_menu_name(self, item=None, label=None):
            if item and item in self.items:
                gobject.idle_add(self.items[item].set_label, label)

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


##[ Common main() logic ]######################################################

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
                #WxWindowsIndicator
                ):
        try:
            indicator = cls()
        except (AssertionError, ImportError, NameError):
            indicator = None
        if indicator:
            indi = indicator(config)
            StdinWatcher(config, indi).start()
            indi.run()
            break
