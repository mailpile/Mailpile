#!/usr/bin/env python2
#
# This is a proof-of-concept quick hack, copy-pasted from code found here:
#
#   http://agateau.com/2012/02/03/pyqtwebkit-experiments-part-2-debugging/
#
import sys
from PySide.QtCore import *
from PySide.QtGui import *
from PySide.QtWebKit import *

class Window(QWidget):
    def __init__(self):
        super(Window, self).__init__()
        self.view = QWebView(self)

        self.setupInspector()

        self.splitter = QSplitter(self)
        self.splitter.setOrientation(Qt.Vertical)

        layout = QVBoxLayout(self)
        #layout.setMargin(0)
        layout.addWidget(self.splitter)

        self.splitter.addWidget(self.view)
        self.splitter.addWidget(self.webInspector)

    def setupInspector(self):
        page = self.view.page()
        page.settings().setAttribute(QWebSettings.DeveloperExtrasEnabled, True)
        self.webInspector = QWebInspector(self)
        self.webInspector.setPage(page)

        #shortcut = QShortcut(self)
        #shortcut.setKey(Qt.Key_F12)
        #shortcut.activated.connect(self.toggleInspector)
        self.webInspector.setVisible(True)

    def toggleInspector(self):
        self.webInspector.setVisible(not self.webInspector.isVisible())

def main():
    app = QApplication(sys.argv)
    window = Window()
    window.show()
    window.view.load('http://localhost:33511/')
    return app.exec_()

sys.exit(main())
