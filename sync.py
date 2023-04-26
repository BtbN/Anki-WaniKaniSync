from aqt import mw
from aqt.operations import CollectionOp
from anki.collection import OpChangesWithCount
from anki.consts import QUEUE_TYPE_NEW, QUEUE_TYPE_LRN, QUEUE_TYPE_REV, QUEUE_TYPE_SUSPENDED, CARD_TYPE_NEW, CARD_TYPE_LRN, CARD_TYPE_REV

from .wk_api import wk_api_req
from .importer import ensure_notes, ensure_deck, convert_wk3_notes, sort_new_cards
from .utils import wknow, wkparsetime, report_progress


def get_available_subject_ids(config):
    req = "assignments?unlocked=true&hidden=false"

    last_sync = config["_LAST_ASSIGNMENTS_SYNC"]
    if last_sync:
        req += "&updated_after=" + last_sync

    report_progress("Fetching unlocked assignments...", 0, 0)

    config["_LAST_ASSIGNMENTS_SYNC"] = wknow()
    assignments = wk_api_req(req)

    return [data["data"]["subject_id"] for data in assignments["data"]]


def get_existing_subject_ids(config):
    existing_note_ids = mw.col.find_notes(f'"note:{config["NOTE_TYPE_NAME"]}"')
    return [mw.col.get_note(nid)["card_id"] for nid in existing_note_ids]


def fetch_subjects(config, subject_ids=None, existing_subject_ids=None, max_lvl=3):
    if not subject_ids:
        subject_ids = [None]
    if not existing_subject_ids:
        existing_subject_ids = [None]

    last_sync = config["_LAST_SUBJECTS_SYNC"]
    config["_LAST_SUBJECTS_SYNC"] = wknow()

    subjects = {}
    chunk_size = 1000
    existing = True
    for current_ids in [existing_subject_ids, subject_ids]:
        # Just skip existing subjects if they're empty (there just are none) or if
        # the subject_ids are empty, meaning we are about to fetch all subjects anyway.
        if existing and (not existing_subject_ids[0] or not subject_ids[0]):
            existing = False
            continue

        for i in range(0, len(current_ids), chunk_size):
            chunk_ids = current_ids[i:i+chunk_size]

            req = "subjects?levels=" + ",".join([str(i) for i in range(max_lvl + 1)])
            if chunk_ids[0]:
                req += "&ids=" + ",".join(str(id) for id in chunk_ids)

            # Include the update-limit if:
            #  - we have a last sync timestamps AND
            #    - we are synching existing subjects in the database OR
            #    - we are fetching ALL subjects, in which case existing subjects were skipped
            if last_sync and (existing or not current_ids[0]):
                req += "&updated_after=" + last_sync

            report_progress(f"Fetching subjects {i}/{len(current_ids)}...", 0, 0)

            sub_subjects = wk_api_req(req)
            for subject in sub_subjects["data"]:
                subjects[subject["id"]] = subject
        existing = False

    report_progress("Done fetching subjects...", 0, 0)

    return list(subjects.values())


def fetch_sub_subjects(config, subjects):
    sub_subject_ids = set()
    for subject in subjects:
        if "amalgamation_subject_ids" in subject["data"]:
            for id in subject["data"]["amalgamation_subject_ids"]:
                sub_subject_ids.add(id)
        if "component_subject_ids" in subject["data"]:
            for id in subject["data"]["component_subject_ids"]:
                sub_subject_ids.add(id)
        if "visually_similar_subject_ids" in subject["data"]:
            for id in subject["data"]["visually_similar_subject_ids"]:
                sub_subject_ids.add(id)

    # Collect subjects which are in the already fetched list
    sub_subjects = {}
    for subj in subjects:
        if subj["id"] in sub_subject_ids:
            sub_subjects[subj["id"]] = subj
            sub_subject_ids.remove(subj["id"])

    #TODO: Maybe reconstruct minimal sub-subjects from the existing notes, to avoid extra API calls?

    # Download missing ones from WK
    chunk_size = 1000
    sub_subject_ids = list(sub_subject_ids)
    for i in range(0, len(sub_subject_ids), chunk_size):
        cur_ids = sub_subject_ids[i:i+chunk_size]

        req = "subjects?ids=" + ",".join(str(id) for id in cur_ids)

        report_progress(f"Fetching sub-subjects {i}/{len(sub_subject_ids)}...", 0, 0)
        res_subjects = wk_api_req(req)

        for subject in res_subjects["data"]:
            sub_subjects[subject["id"]] = subject

    report_progress("Done fetching sub-subjects...", 0, 0)

    return sub_subjects


def update_due_time_from_assignment(config, col, assignment, learn_ahead_secs):
    subject_id = assignment["data"]["subject_id"]
    card_ids = col.find_cards(f'"note:{config["NOTE_TYPE_NAME"]}" "deck:{config["DECK_NAME"]}" card\\_id:{subject_id}')
    if not card_ids:
        return

    if assignment["data"]["burned_at"]:
        # Card is burned: make it a review card, and leave alone due time
        card_type = CARD_TYPE_REV
        card_queue = QUEUE_TYPE_REV
        card_due = None
    elif not assignment["data"]["unlocked_at"]:
        # Card is not unlocked: suspend it
        card_type = CARD_TYPE_NEW
        card_queue = QUEUE_TYPE_SUSPENDED
        card_due = 0
    elif not assignment["data"]["available_at"]:
        # Card is in lesson mode: make it a new card
        card_type = CARD_TYPE_NEW
        card_queue = QUEUE_TYPE_NEW
        card_due = 0
    else:
        # Card is in a srs stage: make it a learning card, set due to precise timestamp
        card_type = CARD_TYPE_LRN
        card_queue = QUEUE_TYPE_LRN

        avail_at = wkparsetime(assignment["data"]["available_at"])
        card_due = int(avail_at.timestamp()) + learn_ahead_secs

    cards = []
    for card_id in card_ids:
        card = col.get_card(card_id)
        card.type = card_type
        card.queue = card_queue

        if card_due is not None:
            card.due = card_due

        cards.append(card)

    col.update_cards(cards)
    return len(cards)


def sync_assignment_dues(config, col):
    last_sync = config["_LAST_DUE_SYNC"]
    config["_LAST_DUE_SYNC"] = wknow()

    report_progress("Syncing due times...", 0, 0)

    req = "assignments?hidden=false"
    if last_sync:
        req += "&updated_after=" + last_sync
    res = wk_api_req(req)

    learn_ahead_secs = col.get_preferences().scheduling.learn_ahead_secs

    i = 0
    cnt = 0
    for assignment in res["data"]:
        i += 1
        report_progress(f'Updating due times {i}/{res["total_count"]}...', i, res["total_count"])
        cnt += update_due_time_from_assignment(config, col, assignment, learn_ahead_secs)

    return cnt


def do_sync_op(col):
    config = mw.addonManager.getConfig(__name__)

    if not config["WK_API_KEY"]:
        raise Exception("Configure your WaniKani API key first.")

    user_data = wk_api_req("user")
    granted_lvl = user_data["data"]["subscription"]["max_level_granted"]

    subject_ids = None
    existing_subject_ids = None
    if not config["SYNC_ALL"]:
        subject_ids = get_available_subject_ids(config)
        existing_subject_ids = get_existing_subject_ids(config)

    subjects = fetch_subjects(config, subject_ids, existing_subject_ids, granted_lvl)
    sub_subjects = fetch_sub_subjects(config, subjects)

    result = OpChangesWithCount()
    result.count = len(subjects)

    if ensure_deck(col, config["NOTE_TYPE_NAME"], config["DECK_NAME"]):
        result.changes.notetype = True
        result.changes.deck = True
        result.changes.deck_config = True

    if ensure_notes(col, subjects, sub_subjects, config["NOTE_TYPE_NAME"], config["DECK_NAME"]):
        result.changes.card = True
        result.changes.note = True

    if config["SYNC_DUE_TIME"]:
        if sync_assignment_dues(config, col) > 0:
            result.changes.study_queues = True

    if result.changes.card or result.changes.study_queues:
        report_progress("Sorting deck...", 100, 100)
        sort_new_cards(col, config["DECK_NAME"])

    mw.addonManager.writeConfig(__name__, config)

    return result


def do_convert_wk3_op(col):
    config = mw.addonManager.getConfig(__name__)

    if not config["WK_API_KEY"]:
        raise Exception("Configure your WaniKani API key first.")

    user_data = wk_api_req("user")
    granted_lvl = user_data["data"]["subscription"]["max_level_granted"]

    result = OpChangesWithCount()

    if ensure_deck(col, config["NOTE_TYPE_NAME"], config["DECK_NAME"]):
        result.changes.notetype = True
        result.changes.deck = True
        result.changes.deck_config = True

    config["_LAST_SUBJECTS_SYNC"] = ""
    subjects = fetch_subjects(config, None, None, granted_lvl)
    sub_subjects = fetch_sub_subjects(config, subjects)

    result.count = len(subjects)

    convert_wk3_notes(col, subjects, config["NOTE_TYPE_NAME"])

    if ensure_notes(col, subjects, sub_subjects, config["NOTE_TYPE_NAME"], config["DECK_NAME"]):
        result.changes.card = True
        result.changes.note = True

    if result.changes.card:
        report_progress("Sorting deck...", 100, 100)
        sort_new_cards(col, config["DECK_NAME"])

    config["SYNC_ALL"] = True
    config["SYNC_DUE_TIME"] = False
    mw.addonManager.writeConfig(__name__, config)

    return result


def do_sync():
    CollectionOp(mw, do_sync_op).run_in_background()


def do_convert_wk3():
    CollectionOp(mw, do_convert_wk3_op).run_in_background()


def auto_sync():
    config = mw.addonManager.getConfig(__name__)
    if not config["WK_API_KEY"] or not config["AUTO_REPORT"]:
        return
    do_sync()
