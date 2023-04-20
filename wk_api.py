from aqt import mw

import requests


WK_API_BASE="https://api.wanikani.com/v2"
WK_REV="20170710"


def wk_api_req(ep):
    config = mw.addonManager.getConfig(__name__)
    api_key = config["WK_API_KEY"]
    if not api_key:
        raise Exception("No API Key!")

    headers = {
        "Authorization": "Bearer " + api_key,
        "Wanikani-Revision": WK_REV
    }

    res = requests.get(f"{WK_API_BASE}/{ep}", headers=headers)
    res.raise_for_status()
    data = res.json()

    if "object" in data and data["object"] == "collection":
        next_url = data["pages"]["next_url"]
        while next_url:
            res = requests.get(next_url, headers=headers)
            res.raise_for_status()
            new_data = res.json()

            data["data"] += new_data["data"]
            next_url = new_data["pages"]["next_url"]

    return data
