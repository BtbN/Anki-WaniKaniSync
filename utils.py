from datetime import datetime, timezone
from aqt import mw


def wknow():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def report_progress(txt, val, max):
     mw.taskman.run_on_main(
        lambda: mw.progress.update(
            label=txt,
            value=val,
            max=max
        )
     )
