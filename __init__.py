from aqt import mw, gui_hooks
from aqt.utils import showInfo, qconnect
from aqt.qt import *

from datetime import datetime, timezone
import pathlib

from .wk_api import wk_api_req


def wknow():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def ensure_deck(note_name, deck_name):
    model = mw.col.models.by_name(note_name)
    if not model:
        model = mw.col.models.new(note_name)

        fields = [
            "card_id", "sort_id", "Characters", "Card_Type", "Word_Type",
            "Meaning", "Meaning_Mnemonic", "Meaning_Hint", "Meaning_Whitelist",
            "Reading", "Reading_Onyomi", "Reading_Kunyomi", "Reading_Nanori", "Reading_Mnemonic", "Reading_Hint",
            "Components_Characters", "Components_Meaning", "Components_Reading",
            "Similar_Characters", "Similar_Meaning", "Similar_Reading",
            "Found_in_Characters", "Found_in_Meaning", "Found_in_Reading",
            "Context_Patterns", "Context_Sentences",
            "Audio"
        ]
        for field in fields:
            mw.col.models.add_field(model, mw.col.models.new_field(field))

        datadir = pathlib.Path(__file__).parent.resolve() / "data"

        meaning_tpl = mw.col.models.new_template("Meaning")
        meaning_tpl["qfmt"] = (datadir / "meaning_front.html").read_text(encoding="utf-8")
        meaning_tpl["afmt"] = (datadir / "meaning_back.html").read_text(encoding="utf-8")
        mw.col.models.add_template(model, meaning_tpl)

        showInfo(meaning_tpl["qfmt"])
        showInfo(meaning_tpl["afmt"])

        reading_tpl = mw.col.models.new_template("Reading")
        reading_tpl["qfmt"] = (datadir / "reading_front.html").read_text(encoding="utf-8")
        reading_tpl["afmt"] = (datadir / "reading_back.html").read_text(encoding="utf-8")
        mw.col.models.add_template(model, reading_tpl)

        showInfo(reading_tpl["qfmt"])
        showInfo(reading_tpl["afmt"])

        model["css"] = (datadir / "style.css").read_text(encoding="utf-8")

        mw.col.models.add_dict(model)
        model = mw.col.models.by_name(note_name)

    deck_id = mw.col.decks.id(deck_name, create=False)
    if not deck_id:
        deck_id = mw.col.decks.id(deck_name, create=True)
        deck = mw.col.decks.get(deck_id)
        deck["mid"] = model["id"]
        mw.col.decks.save(deck)


def get_available_subject_ids(config):
    req = "assignments?unlocked=true&hidden=false"
    if config["_LAST_ASSIGNMENTS_SYNC"]:
        req += "&updated_after=" + config["_LAST_ASSIGNMENTS_SYNC"]

    config["_LAST_ASSIGNMENTS_SYNC"] = wknow()
    assignments = wk_api_req(req)

    subject_ids = [data["data"]["subject_id"] for data in assignments["data"]]
    #TODO: fetch existing subject IDs from notes, since only updated ones will appear here

    return subject_ids


def do_sync():
    config = mw.addonManager.getConfig(__name__)

    if not config["WK_API_KEY"]:
        showInfo("Configure your WaniKani API key first.")
        return

    user_data = wk_api_req("user")
    granted_lvl = user_data["data"]["subscription"]["max_level_granted"]

    subject_ids = get_available_subject_ids(config)

    last_sync = config["_LAST_SUBJECTS_SYNC"]
    config["_LAST_SUBJECTS_SYNC"] = wknow()

    subjects = []
    chunk_size = 500
    for i in range(0, len(subject_ids), chunk_size):
        sub_subject_ids = subject_ids[i:i+chunk_size]

        req = "subjects?hidden=false"
        if last_sync:
            req += "&updated_after=" + last_sync
        if sub_subject_ids[0]:
            req += "&ids=" + ",".join(str(id) for id in sub_subject_ids)

        sub_subjects = wk_api_req(req)
        subjects += sub_subjects["data"]

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
