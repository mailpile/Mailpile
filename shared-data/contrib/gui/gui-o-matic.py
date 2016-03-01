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

    ICON_THEME = 'light'

    def __init__(self, config):
        self.config = config
        self.ready = False
        self._webview = None

    def _do(self, op, args):
        op, args = op.lower(), args[:]

        if op == 'show_url':
            self.show_url(url=args[0])

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

    def _theme_image(self, pathname):
        return pathname.replace('%(theme)s', self.ICON_THEME)

    def _add_menu_item(self, item='item', label='Menu item', sensitive=False,
                             op=None, args=None, **ignored_kwargs):
        pass

    def _create_menu_from_config(self):
        for item_info in self.config.get('indicator_menu', []):
            self._add_menu_item(**item_info)

    def _set_status(self, status):
        print 'STATUS: %s' % status

    def set_status_startup(self):
        self._set_status('startup')

    def set_status_normal(self):
        self._set_status('normal')

    def set_status_working(self):
        self._set_status('working')

    def set_status_attention(self):
        self._set_status('attention')

    def set_status_shutdown(self):
        self._set_status('shutdown')

    def set_menu_label(self, item=None, label=None):
        pass

    def set_menu_sensitive(self, item=None, sensitive=True):
        pass

    def update_splash_screen(self, message=None, progress=None):
        pass

    def show_splash_screen(self, height=None, width=None,
                           progress_bar=False, image=None, message=None):
        pass

    def _get_webview(self):
        return None

    def show_url(self, url=None):
        assert(url is not None)
        if not self.config.get('external_browser'):
            webview = self._get_webview()
            if webview:
                return webview.show_url(url)
        webbrowser.open(url)

    def hide_splash_screen(self):
        pass

    def notify_user(self, message='Hello'):
        print 'NOTIFY: %s' % message


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

    ICON_THEME = 'light'

    gobject.threads_init()

    class UnityWebView():
        def __init__(self, mpi):
            import webkit
            self.webview = webkit.WebView()

            self.scroller = gtk.ScrolledWindow()
            self.scroller.add(self.webview)

            self.vbox = gtk.VBox(False, 1)
            self.vbox.pack_start(self.scroller, True, True)

            self.window = gtk.Window(gtk.WINDOW_TOPLEVEL)
            self.window.set_size_request(1100, 600)
            self.window.connect('delete-event', lambda w, e: w.hide() or True)
            self.window.add(self.vbox)

            self.browser_settings = self.webview.get_settings()
            self.browser_settings.set_property("enable-java-applet", False)
            self.browser_settings.set_property("enable-plugins", False)
            self.browser_settings.set_property("enable-scripts", True)
            self.browser_settings.set_property("enable-private-browsing", True)
            self.browser_settings.set_property("enable-spell-checking", True)
            self.browser_settings.set_property("enable-developer-extras", True)
            self.webview.set_settings(self.browser_settings)

        def show_url(self, url):
            self.webview.open('about:blank')  # Clear page while loading
            self.webview.open(url)
            self.window.show_all()

    class MailpileIndicator(Indicator):
        def __init__(self, config):
            Indicator.__init__(self, config)
            self.splash = None

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
                # FIXME: Make these two configurable...
                "indicator-messages", appindicator.CATEGORY_COMMUNICATIONS)
            self._set_status('startup', now=True)
            self.ind.set_menu(self.menu)

        def update_splash_screen(self, progress=None, message=None):
            if self.splash:
                if message is not None and 'message' in self.splash:
                    self.splash['message'].set_markup(message)
                if progress is not None and 'progress' in self.splash:
                    self.splash['progress'].set_fraction(progress)

        def show_splash_screen(self, height=None, width=None,
                               progress_bar=False, image=None, message=None,
                               now=False):
            def show(self):
                window = gtk.Window(gtk.WINDOW_TOPLEVEL)
                vbox = gtk.VBox(False, 1)

                if message:
                    lbl = gtk.Label()
                    lbl.set_markup(message or '')
                    lbl.set_alignment(0.5, 0.5)
                    vbox.pack_start(lbl, True, True)
                else:
                    lbl = None

                if image:
                    themed_image = self._theme_image(image)
                    img = gtk.gdk.pixbuf_new_from_file(themed_image)
                    def draw_background(widget, ev):
                        alloc = widget.get_allocation()
                        pb = img.scale_simple(alloc.width, alloc.height,
                                              gtk.gdk.INTERP_BILINEAR)
                        widget.window.draw_pixbuf(
                            widget.style.bg_gc[gtk.STATE_NORMAL],
                            pb, 0, 0, alloc.x, alloc.y)
                        if (hasattr(widget, 'get_child') and
                                widget.get_child() is not None):
                            widget.propagate_expose(widget.get_child(), ev)
                        return False
                    vbox.connect('expose_event', draw_background)

                if progress_bar:
                    pbar = gtk.ProgressBar()
                    pbar.set_orientation(gtk.PROGRESS_LEFT_TO_RIGHT)
                    vbox.pack_end(pbar, False, True)
                else:
                    pbar = None

                window.set_title(self.config['app_name'])
                window.set_decorated(False)
                window.set_position(gtk.WIN_POS_CENTER)
                window.set_size_request(width or 240, height or 320)
                window.add(vbox)
                window.show_all()

                self.hide_splash_screen(now=True)
                self.splash = {
                    'window': window,
                    'vbox': vbox,
                    'message': lbl,
                    'progress': pbar
                }
            if now:
                show(self)
            else:
                gobject.idle_add(show, self)

        def hide_splash_screen(self, now=False):
            def hide(self):
                for k in self.splash or []:
                    if self.splash[k] is not None:
                        self.splash[k].destroy()
                self.splash = None
            if now:
                hide(self)
            else:
                gobject.idle_add(hide, self)

        def _get_webview(self):
            if not self._webview:
                try:
                    self._webview = UnityWebView(self)
                except ImportError:
                    pass
            return self._webview

        def notify_user(self, message='Hello'):
            if pynotify:
                notification = pynotify.Notification(
                    "Mailpile", message, "dialog-warning")
                notification.set_urgency(pynotify.URGENCY_NORMAL)
                notification.show()
            else:
                print 'FIXME: Notify: %s' % message

        _STATUS_MODES = {
            'startup': appindicator.STATUS_ACTIVE,
            'normal': appindicator.STATUS_ACTIVE,
            'working': appindicator.STATUS_ACTIVE,
            'attention': appindicator.STATUS_ATTENTION,
            'shutdown': appindicator.STATUS_ATTENTION,
        }
        def _set_status(self, mode, now=False):
            if now:
                do = lambda o, a: o(a)
            else:
                do = gobject.idle_add
            if 'indicator_icons' in self.config:
                icon = self.config['indicator_icons'].get(mode)
                if not icon:
                    icon = self.config['indicator_icons'].get('normal')
                if icon:
                    do(self.ind.set_icon, self._theme_image(icon))
            do(self.ind.set_status, self._STATUS_MODES[mode])

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
    from PyObjCTools import AppHelper
except ImportError:
    objc = None


def MacOSXIndicator():
    assert(objc is not None)

    class MacOSXThing(NSObject):
        indicator = None

        def applicationDidFinishLaunching_(self, notification):
            self.indicator._menu_setup()
            self.indicator._ind_setup()
            self.indicator.ready = True

        def activate_(self, notification):
            for i, v in self.indicator.items.iteritems():
                if notification == v:
                    if i in self.indicator.callbacks:
                        self.indicator.callbacks[i]()
                    return
            print 'activated an unknown item: %s' % notification

    class MailpileIndicator(Indicator):

        ICON_THEME = 'osx'  # OS X has its own theme because it is too
                            # dumb to auto-resize menu bar icons.

        def _menu_setup(self):
            # Build a very simple menu
            self.menu = NSMenu.alloc().init()
            self.menu.setAutoenablesItems_(objc.NO)
            self.items = {}
            self.callbacks = {}
            self._create_menu_from_config()

        def _add_menu_item(self, item='item', label='Menu item',
                                 sensitive=False,
                                 op=None, args=None,
                                 **ignored_kwarg):
            # For now, bind everything to the notify method
            menuitem = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                label, 'activate:', '')
            menuitem.setEnabled_(sensitive)
            self.menu.addItem_(menuitem)
            self.items[item] = menuitem
            if op:
                def activate(o, a):
                    return lambda: self._do(o, a)
                self.callbacks[item] = activate(op, args or [])

        def _ind_setup(self):
            # Create the statusbar item
            self.ind = NSStatusBar.systemStatusBar().statusItemWithLength_(
                NSVariableStatusItemLength)

            # Load all images, set initial
            self.images = {}
            for s, p in self.config.get('indicator_icons', {}).iteritems():
                p = self._theme_image(p)
                self.images[s] = NSImage.alloc().initByReferencingFile_(p)
            if self.images:
                self.ind.setImage_(self.images['normal'])

            self.ind.setHighlightMode_(1)
            #self.ind.setToolTip_('Sync Trigger')
            self.ind.setMenu_(self.menu)
            self.set_status_startup()

        def _set_status(self, status):
            self.ind.setImage_(self.images.get(status, self.images['normal']))

        def set_menu_label(self, item=None, label=None):
            if item and item in self.items:
                self.items[item].setTitle_(label)

        def set_menu_sensitive(self, item=None, sensitive=True):
            if item and item in self.items:
                self.items[item].setEnabled_(sensitive)

        def notify_user(self, message=None):
            pass  # FIXME

        def run(self):
            app = NSApplication.sharedApplication()
            osxthing = MacOSXThing.alloc().init()
            osxthing.indicator = self
            app.setDelegate_(osxthing)
            try:
                AppHelper.runEventLoop()
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
            time.sleep(0.1)
            while True:
                line = sys.stdin.readline()
                if not line:
                    break
                try:
                    cmd, args = line.split(' ', 1)
                    args = json.loads(args)
                    self.do(cmd, args)
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
            indicator = cls()(config)
            StdinWatcher(config, indicator).start()
            indicator.run()
            break
        except:
            pass
