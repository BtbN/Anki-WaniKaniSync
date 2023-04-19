from aqt import mw
from aqt.utils import showInfo, qconnect
from aqt.qt import *

import requests


def do_sync():
    pass


menu = QMenu("WKSync", mw)
mw.form.menuTools.addMenu(menu)

sync_action = QAction("Sync", mw)
qconnect(sync_action.triggered, do_sync)
menu.addAction(sync_action)
