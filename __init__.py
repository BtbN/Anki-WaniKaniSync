from aqt import mw, gui_hooks
from aqt.utils import showInfo, qconnect
from aqt.qt import *

import requests
from datetime import datetime


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
    data = res.json()

    if "object" in data and data["object"] == "collection":
        next_url = data["pages"]["next_url"]
        while next_url:
            res = requests.get(next_url, headers=headers)
            res.raise_for_status()
            new_data = res.json()

            data["data"] += new_data["data"]
            next_url = new_data["pages"]["next_url"]

    return data


def do_sync():
    if not config["WK_API_KEY"]:
        showInfo("Configure your WaniKani API key first.")
        return

    user_data = wk_api_req("user")
    sync_all = config["SYNC_ALL"]
    granted_lvl = user_data["data"]["subscription"]["max_level_granted"]

    if sync_all:
        pass
    else:
        req = "assignments?unlocked=true&hidden=false"
        if config["_LAST_ASSIGNMENTS_SYNC"]:
            req += "&updated_after=" + config["_LAST_ASSIGNMENTS_SYNC"]
        assignments = wk_api_req(req)



    mw.addonManager.writeConfig(__name__, config)


def analyze_answer(card, ease):
    pass


menu = QMenu("WKSync", mw)
mw.form.menuTools.addMenu(menu)

sync_action = QAction("Sync", mw)
qconnect(sync_action.triggered, do_sync)
menu.addAction(sync_action)


gui_hooks.reviewer_did_answer_card.append(analyze_answer)
