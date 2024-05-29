from aqt import mw

from pyrate_limiter import Duration, Rate, Limiter
from requests.adapters import HTTPAdapter, Retry
from time import sleep
import requests


WK_API_BASE="https://api.wanikani.com/v2"
WK_REV="20170710"

limiter = Limiter(Rate(50, Duration.MINUTE), raise_when_fail=False, max_delay=250)

class WKReqCancelledException(Exception):
    pass

def _do_limit(name):
    while not mw.progress.want_cancel():
        if limiter.try_acquire(name):
            return True
        sleep(limiter.max_delay / 1000)
    raise WKReqCancelledException("The request was cancelled.")

session = requests.Session()
session.mount("https://", HTTPAdapter(max_retries=Retry(total=5, backoff_factor=0.5)))

def wk_api_req(ep, full=True, data=None, put=False, timeout=5):
    config = mw.addonManager.getConfig(__name__)
    api_key = config["WK_API_KEY"]
    if not api_key:
        raise Exception("No API Key!")

    headers = {
        "Authorization": "Bearer " + api_key,
        "Wanikani-Revision": WK_REV
    }

    _do_limit(api_key)

    if data is not None:
        if put:
            res = session.put(f"{WK_API_BASE}/{ep}", headers=headers, json=data, timeout=timeout)
        else:
            res = session.post(f"{WK_API_BASE}/{ep}", headers=headers, json=data, timeout=timeout)
    else:
        res = session.get(f"{WK_API_BASE}/{ep}", headers=headers, timeout=timeout)
    res.raise_for_status()
    data = res.json()

    if full and "object" in data and data["object"] == "collection":
        next_url = data["pages"]["next_url"]
        while next_url:
            if not _do_limit(api_key):
                return None
            res = session.get(next_url, headers=headers, timeout=timeout)
            res.raise_for_status()
            new_data = res.json()

            data["data"] += new_data["data"]
            next_url = new_data["pages"]["next_url"]

    return data
