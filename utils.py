from datetime import datetime, timezone


def wknow():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
