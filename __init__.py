import pathlib
import sys
sys.path.append(str(pathlib.Path(__file__).parent.resolve() / "deps"))

from aqt import mw, gui_hooks
from aqt.qt import *
from aqt.utils import qconnect

from .sync import do_sync, do_convert_wk3, do_clear_cache, auto_sync
from .review import analyze_answer, do_autoreview, auto_autoreview
from .importer import do_update_html

from .play_all_audio import install_play_all_audio


menu = QMenu("WaniKani", mw)
mw.form.menuTools.addMenu(menu)

sync_action = QAction("Sync Notes", mw)
qconnect(sync_action.triggered, do_sync)
menu.addAction(sync_action)

review_action = QAction("Review Mature Cards", mw)
qconnect(review_action.triggered, do_autoreview)
menu.addAction(review_action)

menu.addSeparator()

clear_cache_action = QAction("Clear Cache", mw)
qconnect(clear_cache_action.triggered, do_clear_cache)
menu.addAction(clear_cache_action)

menu.addSeparator()

convert_action = QAction("Convert WK3", mw)
qconnect(convert_action.triggered, do_convert_wk3)
menu.addAction(convert_action)

update_html_action = QAction("Overwrite Card HTML", mw)
qconnect(update_html_action.triggered, do_update_html)
menu.addAction(update_html_action)


just_loaded = False
anki_closing = False

def on_load():
    global just_loaded, anki_closing
    just_loaded = True
    anki_closing = False
gui_hooks.profile_did_open.append(on_load)

def on_close():
    global anki_closing
    anki_closing = True
gui_hooks.profile_will_close.append(on_close)

def on_synced():
    global just_loaded
    if anki_closing:
        return
    if just_loaded:
        auto_sync()
    just_loaded = False
    auto_autoreview()
gui_hooks.sync_did_finish.append(on_synced)

gui_hooks.reviewer_did_answer_card.append(analyze_answer)


install_play_all_audio()
