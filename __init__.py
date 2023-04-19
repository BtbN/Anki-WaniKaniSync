from aqt import mw
from aqt.utils import showInfo, qconnect
from aqt.qt import *

import requests


WK_API_BASE="https://api.wanikani.com/v2"
WK_REV="20170710"

config = mw.addonManager.getConfig(__name__)


def wk_api_req(ep):
    api_key = config["WK_API_KEY"]
    if not api_key:
        raise Exception("No API Key!")

    headers = {
        "Authorization": "Bearer " + api_key,
        "Wanikani-Revision": WK_REV
    }
    
    res = requests.get(f"{WK_API_BASE}/{ep}", headers=headers)
    res.raise_for_status()
    return res.json()


def do_sync():
    if not config["WK_API_KEY"]:
        showInfo("Configure your WaniKani API key first.")
        return

    showInfo(repr(wk_api_req("user")))


menu = QMenu("WKSync", mw)
mw.form.menuTools.addMenu(menu)

sync_action = QAction("Sync", mw)
qconnect(sync_action.triggered, do_sync)
menu.addAction(sync_action)
