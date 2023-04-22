from aqt import mw, gui_hooks
from aqt.utils import showInfo, qconnect
from aqt.operations import CollectionOp, QueryOp
from aqt.qt import *
from anki.collection import OpChanges, OpChangesWithCount

import pathlib
import sys
sys.path.append(str(pathlib.Path(__file__).parent.resolve() / "deps"))

from .wk_api import wk_api_req
from .importer import ensure_notes, ensure_deck
from .utils import wknow, report_progress


def get_available_subject_ids(config):
    req = "assignments?unlocked=true&hidden=false"

    last_sync = config["_LAST_ASSIGNMENTS_SYNC"]
    if last_sync:
        req += "&updated_after=" + last_sync

    config["_LAST_ASSIGNMENTS_SYNC"] = wknow()
    print(req)
    assignments = wk_api_req(req)

    subject_ids = [data["data"]["subject_id"] for data in assignments["data"]]

    #TODO: fetch existing subject IDs from notes, since only updated ones will appear here

    return subject_ids


def fetch_sub_subjects(subject_ids, existing_subjects):
    subjects = {}

    # Collect subjects which are in the already fetched list
    subject_ids = set(subject_ids)
    for subj in existing_subjects:
        if subj["id"] in subject_ids:
            subjects[subj["id"]] = subj
            subject_ids.remove(subj["id"])

    # Download missing ones from WK
    chunk_size = 1000
    subject_ids = list(subject_ids)
    for i in range(0, len(subject_ids), chunk_size):
        sub_subject_ids = subject_ids[i:i+chunk_size]

        req = "subjects?ids=" + ",".join(str(id) for id in sub_subject_ids)

        print(req)
        sub_subjects = wk_api_req(req)

        for subject in sub_subjects["data"]:
            subjects[subject["id"]] = subject

    return subjects


def fetch_subjects(config, subject_ids=None, max_lvl=3):
    if not subject_ids:
        subject_ids = [None]

    last_sync = config["_LAST_SUBJECTS_SYNC"]
    config["_LAST_SUBJECTS_SYNC"] = wknow()

    subjects = []
    chunk_size = 1000
    for i in range(0, len(subject_ids), chunk_size):
        sub_subject_ids = subject_ids[i:i+chunk_size]

        req = "subjects?levels=" + ",".join([str(i) for i in range(max_lvl + 1)])
        if sub_subject_ids[0]:
            req += "&ids=" + ",".join(str(id) for id in sub_subject_ids)
        else:
            req += "&hidden=false"
        if last_sync:
            req += "&updated_after=" + last_sync

        print(req)
        sub_subjects = wk_api_req(req)
        subjects += sub_subjects["data"]

    sub_subject_ids = set()
    final_subjects = []
    for subject in subjects:
        if subject["data"]["level"] <= max_lvl:
            final_subjects.append(subject)
        else:
            continue

        if "amalgamation_subject_ids" in subject["data"]:
            for id in subject["data"]["amalgamation_subject_ids"]:
                sub_subject_ids.add(id)
        if "component_subject_ids" in subject["data"]:
            for id in subject["data"]["component_subject_ids"]:
                sub_subject_ids.add(id)
        if "visually_similar_subject_ids" in subject["data"]:
            for id in subject["data"]["visually_similar_subject_ids"]:
                sub_subject_ids.add(id)

    sub_subjects = fetch_sub_subjects(sub_subject_ids, subjects)

    return final_subjects, sub_subjects


def do_sync_op(col):
    config = mw.addonManager.getConfig(__name__)

    if not config["WK_API_KEY"]:
        raise Exception("Configure your WaniKani API key first.")

    user_data = wk_api_req("user")
    granted_lvl = user_data["data"]["subscription"]["max_level_granted"]

    subject_ids = None
    if not config["SYNC_ALL"]:
        subject_ids = get_available_subject_ids(config)

    subjects, sub_subjects = fetch_subjects(config, subject_ids, granted_lvl)

    result = OpChangesWithCount()
    result.count = len(subjects)

    if ensure_deck(col, config["NOTE_TYPE_NAME"], config["DECK_NAME"]):
        result.changes.notetype = True
        result.changes.deck = True
        result.changes.deck_config = True

    if ensure_notes(col, subjects, sub_subjects, config["NOTE_TYPE_NAME"], config["DECK_NAME"]):
        result.changes.card = True
        result.changes.note = True
        result.changes.note = True
        result.changes.study_queues = True #TODO: maybe move to own function which updates next review time

    mw.addonManager.writeConfig(__name__, config)

    return result


def do_sync():
    CollectionOp(mw, do_sync_op).run_in_background()


def analyze_answer(card, ease):
    pass


menu = QMenu("WaniKani", mw)
mw.form.menuTools.addMenu(menu)

sync_action = QAction("Sync", mw)
qconnect(sync_action.triggered, do_sync)
menu.addAction(sync_action)


gui_hooks.reviewer_did_answer_card.append(analyze_answer)
