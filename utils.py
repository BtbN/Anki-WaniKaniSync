from datetime import datetime, timezone
from aqt import mw
from aqt.utils import tooltip


def wknow():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def wkparsetime(txt):
    return datetime.fromisoformat(txt.replace("Z", "+00:00"))


def report_progress(txt, val, max):
     mw.taskman.run_on_main(
        lambda: mw.progress.update(
            label=txt,
            value=val,
            max=max
        )
     )

def show_tooltip(txt, period=3000):
     mw.taskman.run_on_main(
        lambda: tooltip(txt, period=period)
     )
