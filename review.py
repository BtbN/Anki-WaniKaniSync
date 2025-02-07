from aqt import mw
from aqt.operations import CollectionOp, QueryOp
from anki.collection import OpChanges

import itertools
from datetime import datetime, timezone
from requests.exceptions import HTTPError

from .wk_api import wk_api_req
from .utils import wkparsetime, show_tooltip, report_progress
from .sync import update_due_time_from_assignment


class ReviewException(Exception):
    pass


def update_due_time(config, col, assignment, learn_ahead_secs):
    if col:
        res = OpChanges()
        if update_due_time_from_assignment(config, col, assignment, learn_ahead_secs) > 0:
            res.card = True
            res.study_queues = True
        return res
    else:
        QueryOp(
            parent=mw,
            op=lambda real_col: update_due_time(config, real_col, assignment, learn_ahead_secs),
            success=lambda cnt: None
        ).run_in_background()

def review_subject(config, col, subject_id, assignment=None, learn_ahead_secs=0):
    try:
        if assignment:
            res = { "data": [assignment] }
            subject_id = assignment["data"]["subject_id"]
        else:
            res = wk_api_req(f"assignments?subject_ids={subject_id}&unlocked=true&hidden=false")

        if len(res["data"]) == 0:
            raise ReviewException(f"Assignment for subject {subject_id} not found.")
        elif len(res["data"]) == 1:
            if res["data"][0]["data"]["burned_at"]:
                return False

            started = False
            if not res["data"][0]["data"]["started_at"]:
                res["data"][0] = wk_api_req(f'assignments/{res["data"][0]["id"]}/start', data={}, put=True)
                print(f"Started assignment for subject {subject_id} on WaniKani")
                started = True

            avail_time = res["data"][0]["data"]["available_at"]
            avail_time = wkparsetime(avail_time)

            if avail_time > datetime.now(timezone.utc):
                if not started:
                    raise ReviewException("Failed to submit review to WaniKani:<br/>Card not available for review yet.")
                elif config["SYNC_DUE_TIME"]:
                    update_due_time(config, col, res["data"][0], learn_ahead_secs)
                    return True
                return False

            update_res = wk_api_req("reviews", data={
                "review": {
                    "assignment_id": res["data"][0]["id"]
                }
            })

            if config["SYNC_DUE_TIME"]:
                update_due_time(config, col, update_res["resources_updated"]["assignment"], learn_ahead_secs)
                return True
        else:
            raise ReviewException("Found an unexpected amount of assignments for this card: " + str(len(res["data"])))
    except HTTPError as e:
        if e.response.status_code == 422:
            raise ReviewException(f"Failed submitting review to WaniKani:<br/>Subject {subject_id} likely not ready for review.")
        else:
            raise

    return False


def submit_assignment_op(config, subject_id, learn_ahead_secs):
    res = OpChanges()

    try:
        if review_subject(config, None, subject_id, None, learn_ahead_secs):
            raise Exception("review_subject() made changed when it shouldn't.")

        print(f"Submitted subject {subject_id} review to WaniKani.")
    except ReviewException as e:
        print(str(e))
    except Exception as e:
        show_tooltip(
            "Failed submitting review to WaniKani:<br/>" + str(e),
            period=5000
        )

    return res


def analyze_answer(reviewer, card, ease):
    config = mw.addonManager.getConfig(__name__)
    if not config["WK_API_KEY"] or not config["REPORT_REVIEWS"]:
        return

    if ease < 3:
        return

    note_name = card.note_type()["name"]
    deck_name = mw.col.decks.name(card.current_deck_id())

    if note_name != config["NOTE_TYPE_NAME"] or deck_name != config["DECK_NAME"]:
        return

    note = card.note()
    subject_id = note["card_id"]

    # Analyze sibling cards:
    # If any of the (usually just one) sibling cards are due for review, don't submit.
    card_ids = mw.col.find_cards(f'"deck:{deck_name}" -is:suspended -cid:{card.id} nid:{card.nid} is:due')
    if card_ids:
        print("Not submitting review to WaniKani, a sibling card is due.")
        return

    # If one is not due, but the last answer was again or hard, don't submit either.
    card_ids = mw.col.find_cards(f'"deck:{deck_name}" -is:suspended -cid:{card.id} nid:{card.nid}')
    for card_id in card_ids:
        stats = mw.col.card_stats_data(card_id)
        if len(stats.revlog) <= 0:
            print("Not submitting review to WaniKani, a sibling card never had a review.")
            return

        # It seems like the first revlog item returned is always the latest,
        # but there is no explicit sorting in the SQL query I found in the backend.
        # So sort manually to be sure.
        if max(stats.revlog, key=lambda r: r.time).button_chosen < 3:
            print("Not submitting review to WaniKani, a sibling card has a negative latest review.")
            return

    learn_ahead_secs = mw.col.get_preferences().scheduling.learn_ahead_secs

    QueryOp(
        parent=mw,
        op=lambda col: submit_assignment_op(config, subject_id, learn_ahead_secs),
        success=lambda cnt: None
    ).without_collection().run_in_background()


def autoreview_op(col):
    res = OpChanges()

    config = mw.addonManager.getConfig(__name__)
    if not config["WK_API_KEY"]:
        return res

    user_data = wk_api_req("user")
    granted_lvl = user_data["data"]["subscription"]["max_level_granted"]
    user_lvl = user_data["data"]["level"]

    learn_ahead_secs = col.get_preferences().scheduling.learn_ahead_secs

    available_assignments = {}
    search_nodes = []
    assignments_lessons = wk_api_req("assignments?immediately_available_for_lessons=true")
    assignments_reviews = wk_api_req("assignments?immediately_available_for_review=true")
    for assignment in itertools.chain(assignments_lessons["data"], assignments_reviews["data"]):
        subj_id = assignment["data"]["subject_id"]
        available_assignments[subj_id] = assignment
        search_nodes.append(f"card\\_id:{subj_id}")

    if not search_nodes:
        return res

    search_string = col.build_search_string("-is:suspended", f'"deck:{config["DECK_NAME"]}"', f'"note:{config["NOTE_TYPE_NAME"]}"', col.group_searches(*search_nodes, joiner="OR"))
    note_ids = col.find_notes(search_string)

    ivl_limit = int(config["MATURE_INTERVAL"])

    i = 0
    succ = 0
    for note_id in note_ids:
        i += 1
        report_progress(f"Processing potential reviews {i}/{len(note_ids)}...<br/>{succ} Reviews Submitted", i, len(note_ids))

        note = col.get_note(note_id)
        subj_id = int(note["card_id"])
        assignment = available_assignments[subj_id]

        card_ids = col.find_cards(col.build_search_string("-is:suspended", f'nid:{note_id}', f'"deck:{config["DECK_NAME"]}"'))
        if not len(card_ids):
            print(f"No valid cards for subject {subj_id} one. All suspended?")
            continue

        for card_id in card_ids:
            stats = mw.col.card_stats_data(card_id)
            if len(stats.revlog) <= 0:
                print(f"Card {card_id} has never been reviewed. Not submitting review for {subj_id}.")
                break
            latest = max(stats.revlog, key=lambda r: r.time)
            if latest.button_chosen < 2:
                print(f"Card {card_id} has negative latest review. Not submitting review for {subj_id}.")
                # Only submit reviews for hard or better.
                # Not checking for "good" cause a card with a "hard" review can still have an incredibly long interval.
                break
            wk_due = wkparsetime(assignment["data"]["available_at"] or assignment["data"]["unlocked_at"]).timestamp()
            card = col.get_card(card_id)
            if wk_due > latest.time and card.ivl < ivl_limit:
                print(f"Card {card_id} has not been reviewed({latest.time}) since it became available on WK({wk_due}) and is not mature({card.ivl}<{ivl_limit}). Not submitting review for {subj_id}.")
                # Not reviewed since card became available on WK, don't submit.
                break
        else:
            print(f"Submitting review for {subj_id}.")
            try:
                if review_subject(config, col, subj_id, assignment, learn_ahead_secs):
                    res.card = True
                    res.study_queues = True
                succ += 1
            except ReviewException as e:
                print(str(e))

    return res



def do_autoreview():
    CollectionOp(mw, autoreview_op).run_in_background()


def auto_autoreview():
    config = mw.addonManager.getConfig(__name__)
    if not config["WK_API_KEY"] or not config["_LAST_SUBJECTS_SYNC"]:
        return
    if not config["AUTO_REPORT"]:
        return
    do_autoreview()
