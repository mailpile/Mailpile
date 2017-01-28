#!/usr/bin/python2
from PyQt4 import QtGui, QtCore

import sys ,os
import json
from PyQt4.QtCore import *
from PyQt4.QtGui import *
from PyQt4.QtWebKit import *
from PyQt4.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply
import threading
from subprocess import Popen, PIPE

data = { "unread" :0 , "pass":"123password" , "path" : "" }
process = None
isExiting = False
from os.path import expanduser
home = expanduser("~")
configFile = os.path.join(home,".mailpile","data.json")

def loadJson():
    with open(configFile, 'r') as fp:
        global data
        data = json.load(fp)


def saveJson():
    with open(configFile, 'w') as fp:
        json.dump(data, fp)


class qtWebkit(QWebView):
    def __init__(self):
        QWebView.__init__(self)

        self.timer = QTimer()


    def closeEvent(self, evnt):
        if isExiting:
            self.exit()
        else:
            evnt.ignore()
            self.hide()
            self.setWindowState(QtCore.Qt.WindowMinimized)

    def changeEvent(self, event):
       if event.type() == QtCore.QEvent.WindowStateChange:
           if self.windowState() & QtCore.Qt.WindowMinimized:
               print('changeEvent: Minimized')

           elif event.oldState() & QtCore.Qt.WindowMinimized:
               print('changeEvent: Normal/Maximised/FullScreen')


       QWebView.changeEvent(self, event)

    def close(self):
        isExiting = True
        exit()

    def exit(self):
        saveJson()
        self.timer.stop()
        quitServer()
        QApplication.quit()
        sys.exit(0)


    def restore(self):
        self.show()
        if self.windowState() & QtCore.Qt.WindowMinimized:
            # Window is minimised. Restore it.
            self.setWindowState(Qt.WindowNoState)
            self.activateWindow()

    def loadFinished(self,url,trayIcon):
        frame = self.page().mainFrame()
        document = frame.documentElement()
        try:
            if( "auth" in str(url) and data["pass"] != "123password"):
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
        except Exception, err:
            print err

class SystemTrayIcon(QtGui.QSystemTrayIcon):

    def __init__(self, icon, parent=None):
        QtGui.QSystemTrayIcon.__init__(self, icon, parent)
        menu = QtGui.QMenu(parent)
        self.activated.connect(lambda: menu.exec_(QCursor.pos()))
        self.unreadAction = menu.addAction(str(data["unread"])+" Unread Mail")
        self.showAction = menu.addAction("Show")
        self.exitAction = menu.addAction("Exit")
        self.exitAction.triggered.connect(parent.close)
        self.showAction.triggered.connect(parent.restore)
        self.unreadAction.triggered.connect(parent.restore)
        self.setContextMenu(menu)


    def updateNotifications(self,webview):
        try:
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
        except Exception,err:
            print err


def main(http_url,args=[]):
    loadJson()
    runServer()


    app = QApplication(sys.argv)
    global web
    web = qtWebkit()

    style = app.style()
    icon = QIcon.fromTheme("mail-read")
    trayIcon = SystemTrayIcon(QtGui.QIcon(icon), web)


    icon = QIcon.fromTheme("mail-unread")  # QtGui.QIcon('test_icon.png')
    web.setWindowIcon(icon)
    web.load(QUrl(http_url))
    web.connect(web, QtCore.SIGNAL('loadFinished(bool)'), lambda:web.loadFinished(web.url(),trayIcon))
    web.setWindowTitle('Mailpile')
    web.resize(1000, 650)

    if('-d' in args):
        pass
    else:
        web.show()
    # web.thread.launchServer()

    trayIcon.show()


    web.timer.timeout.connect(lambda:trayIcon.updateNotifications(web))
    web.timer.start(1000)

    sys.exit(app.exec_())


def runServer():
    global process
    appPath = os.path.join(data["path"], "mailpile","app.py")
    process = Popen(['python2', appPath],stdin=PIPE,)
    # stdout, stderr = process.communicate()


if __name__ == "__main__":
    main("http://localhost:33411/",sys.argv[1:])
