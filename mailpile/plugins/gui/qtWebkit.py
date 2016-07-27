
from PyQt4 import QtGui, QtCore

import sys
import cPickle as pickle
from PyQt4.QtCore import *
from PyQt4.QtGui import *
from PyQt4.QtWebKit import *
from PyQt4.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply

data = { "unread" :0 , "pass":" " }
import json

def loadJson():
    with open('/home/harindu/.mailpile/data.json', 'r') as fp:
        global data
        data = json.load(fp)


def saveJson():
    with open('/home/harindu/.mailpile/data.json', 'w') as fp:
        json.dump(data, fp)


class qtWebkit(QWebView):
    def __init__(self):
        QWebView.__init__(self);

    def changeEvent(self, event):
       if event.type() == QtCore.QEvent.WindowStateChange:
           if self.windowState() & QtCore.Qt.WindowMinimized:
               print('changeEvent: Minimised')

           elif event.oldState() & QtCore.Qt.WindowMinimized:
               print('changeEvent: Normal/Maximised/FullScreen')


       QWebView.changeEvent(self, event)

    def closeEvent(self, evnt):
        if True:
            self.exit()
        else:
            evnt.ignore()
            self.setWindowState(QtCore.Qt.WindowMinimized)

    def exit(self):
        saveJson()
        QtCore.QCoreApplication.instance().quit()


    def restore(self):
        if self.windowState() & QtCore.Qt.WindowMinimized:
            # Window is minimised. Restore it.
            self.setWindowState(Qt.WindowNoState)
            self.activateWindow()

    def loadFinished(self,url,trayIcon):
        frame = self.page().mainFrame()
        document = frame.documentElement()

        if( "auth" in str(url)):
            search = document.findFirst("input[id=login-passphrase]")
            search.setAttribute("value", data["pass"])
            button = document.findFirst("button[class=submit]")
            if(button):
                button.evaluateJavaScript("this.click()")

        elif ("profiles" in str(url) or "inbox" in str(url) ):
            print "Inbox is loaded"
            label = document.findFirst("a[data-icon=icon-inbox]")
            data["unread"]= int(label.attribute("data-new"))
            trayIcon.updateNotifications(self)


class SystemTrayIcon(QtGui.QSystemTrayIcon):

    def __init__(self, icon, parent=None):
        QtGui.QSystemTrayIcon.__init__(self, icon, parent)
        menu = QtGui.QMenu(parent)
        self.activated.connect(lambda: menu.exec_(QCursor.pos()))
        self.unreadAction = menu.addAction(str(data["unread"])+" Unread Mail")
        self.showAction = menu.addAction("Show")
        self.exitAction = menu.addAction("Exit")
        self.exitAction.triggered.connect(parent.exit)
        self.showAction.triggered.connect(parent.restore)
        self.unreadAction.triggered.connect(parent.restore)
        self.setContextMenu(menu)


    def updateNotifications(self,webview):
        frame = webview.page().mainFrame()
        document = frame.documentElement()
        label = document.findFirst("a[data-icon=icon-inbox]")
        unreadCurrent = int(label.attribute("data-new"))
        self.unreadAction.setText(str(unreadCurrent)+" Unread Mail" )

        if (unreadCurrent> data["unread"]):
            data["unread"] =unreadCurrent
            self.setIcon(QIcon.fromTheme("mail-new"))
        elif(unreadCurrent>0):
            data["unread"] =unreadCurrent
            self.setIcon(QIcon.fromTheme("mail-unread"))
        else:
            self.setIcon(QIcon.fromTheme("mail-read"))



def main(http_url):

    loadJson()

    app = QApplication(sys.argv)

    web = qtWebkit()

    style = app.style()
    icon = QIcon.fromTheme("mail-read")
    trayIcon = SystemTrayIcon(QtGui.QIcon(icon), web)

    web.load(QUrl(http_url))
    web.connect(web, QtCore.SIGNAL('loadFinished(bool)'), lambda:web.loadFinished(web.url(),trayIcon))
    web.setWindowTitle('Mailpile')
    web.show()

    trayIcon.show()

    timer = QTimer()
    timer.timeout.connect(lambda: trayIcon.updateNotifications(web))
    timer.start(1000)

    sys.exit(app.exec_())







if __name__ == '__main__':
    main("http://google.lk")
