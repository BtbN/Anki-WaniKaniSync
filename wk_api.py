from aqt import mw

from pyrate_limiter import Duration, RequestRate, Limiter
from requests.adapters import HTTPAdapter, Retry
import requests


WK_API_BASE="https://api.wanikani.com/v2"
WK_REV="20170710"

limiter = Limiter(RequestRate(50, Duration.MINUTE))

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

    with limiter.ratelimit(api_key, delay=True):
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
            with limiter.ratelimit(api_key, delay=True):
                res = session.get(next_url, headers=headers, timeout=timeout)
            res.raise_for_status()
            new_data = res.json()

            data["data"] += new_data["data"]
            next_url = new_data["pages"]["next_url"]

    return data
