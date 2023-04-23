import pathlib
import sys
sys.path.append(str(pathlib.Path(__file__).parent.resolve() / "deps"))

from aqt import mw, gui_hooks
from aqt.qt import *
from aqt.utils import qconnect

from .sync import do_sync, do_convert_wk3
from .review import analyze_answer, do_autoreview


menu = QMenu("WaniKani", mw)
mw.form.menuTools.addMenu(menu)

sync_action = QAction("Sync Notes", mw)
qconnect(sync_action.triggered, do_sync)
menu.addAction(sync_action)

review_action = QAction("Review Mature Cards", mw)
qconnect(review_action.triggered, do_autoreview)
menu.addAction(review_action)

convert_action = QAction("Convert WK3", mw)
qconnect(review_action.convert_action, do_convert_wk3)
menu.addAction(convert_action)


gui_hooks.reviewer_did_answer_card.append(analyze_answer)
