from aqt import mw, gui_hooks
from aqt.utils import showInfo, qconnect
from aqt.qt import *

import pathlib
import sys
sys.path.append(str(pathlib.Path(__file__).parent.resolve() / "deps"))

from .wk_api import wk_api_req
from .importer import ensure_cards, ensure_deck
from .utils import wknow


def get_available_subject_ids(config):
    req = "assignments?unlocked=true&hidden=false"

    last_sync = config["_LAST_ASSIGNMENTS_SYNC"]
    if last_sync:
        req += "&updated_after=" + last_sync

    config["_LAST_ASSIGNMENTS_SYNC"] = wknow()
    assignments = wk_api_req(req)

    subject_ids = [data["data"]["subject_id"] for data in assignments["data"]]

    #TODO: fetch existing subject IDs from notes, since only updated ones will appear here

    return subject_ids


def fetch_subjects(subject_ids=None):
    if not subject_ids:
        subject_ids = [None]

    last_sync = config["_LAST_SUBJECTS_SYNC"]
    config["_LAST_SUBJECTS_SYNC"] = wknow()

    subjects = []
    chunk_size = 500
    for i in range(0, len(subject_ids), chunk_size):
        sub_subject_ids = subject_ids[i:i+chunk_size]

        req = "subjects?hidden=true"
        if last_sync:
            req += "&updated_after=" + last_sync
        if sub_subject_ids[0]:
            req += "&ids=" + ",".join(str(id) for id in sub_subject_ids)

        sub_subjects = wk_api_req(req)
        subjects += sub_subjects["data"]

    #TODO: Resolve Sub-Subjects from notes or WK API, such related kanji/radicals/...

    return subjects


def do_sync():
    config = mw.addonManager.getConfig(__name__)

    if not config["WK_API_KEY"]:
        showInfo("Configure your WaniKani API key first.")
        return

    user_data = wk_api_req("user")
    granted_lvl = user_data["data"]["subscription"]["max_level_granted"]

    subject_ids = None
    if not config["SYNC_ALL"]:
        subject_ids = get_available_subject_ids(config)

    subjects = fetch_subjects(subject_ids)

    ensure_deck(config["NOTE_TYPE_NAME"], config["DECK_NAME"])
    ensure_cards(subjects)

    mw.addonManager.writeConfig(__name__, config)


def analyze_answer(card, ease):
    pass


menu = QMenu("WKSync", mw)
mw.form.menuTools.addMenu(menu)

sync_action = QAction("Sync", mw)
qconnect(sync_action.triggered, do_sync)
menu.addAction(sync_action)


gui_hooks.reviewer_did_answer_card.append(analyze_answer)
