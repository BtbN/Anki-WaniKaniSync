#!/usr/bin/env python3
import xml.etree.ElementTree as ET
import requests
import tarfile
import json
import sys
import re

# Needed by requests to decode 10ten data
try:
    import brotli
except ImportError:
    import brotlicffi


def fetch_10ten_data():
    s = requests.Session()
    req = s.get("https://data.10ten.life/jpdict/reader/version-en.json")
    req.raise_for_status()
    version_info = req.json()

    major = "2"
    minor = version_info["words"][major]["minor"]
    patch = version_info["words"][major]["patch"]
    parts = version_info["words"][major]["parts"]

    res = dict()

    # format from: https://github.com/birchill/jpdict-idb/blob/main/src/words.ts
    for part in range(1, parts + 1):
        req = s.get(f"https://data.10ten.life/jpdict/reader/words/en/{major}.{minor}.{patch}-{part}.jsonl")
        req.raise_for_status()
        for line in req.iter_lines():
            data = json.loads(line)
            if "type" in data and data["type"] == "header":
                continue
            if "rm" not in data or "k" not in data or "r" not in data:
                continue

            k = data["k"]
            r = data["r"]
            rm = data["rm"]

            rn = []
            rmn = []
            for i in range(0, min(len(r), len(rm))):
                if not rm[i] or "a" not in rm[i]:
                    continue

                if "app" in rm[i] and rm[i]["app"] == 0:
                    continue

                a = rm[i]["a"]
                if isinstance(a, int):
                    rmn.append(str(a))
                else:
                    rmn.append(str(a[0]["i"]))

                rn.append(r[i])

            if not rn:
                continue

            for reading in k:
                if reading not in res:
                    res[reading] = dict()
                for pair in zip(rn, rmn):
                    if pair[0] not in res[reading]:
                        res[reading][pair[0]] = str(pair[1])

    return res

def fetch_wadoku_data():
    req = requests.get("https://www.wadoku.de/downloads/xml-export/wadoku-xml-latest.tar.xz", stream=True)
    req.raise_for_status()

    tree = None
    with tarfile.open(fileobj=req.raw, mode="r|xz") as tf:
        for member in tf:
            if member.name.endswith("/wadoku.xml"):
                with tf.extractfile(member) as contents:
                    tree = ET.parse(contents)
                break
    if tree is None:
        raise Exception("No wadoku.xml found!")

    root = tree.getroot()

    ns = {"": "http://www.wadoku.de/xml/entry"}
    hira_reg = re.compile(r"(\[Akz\]|[ぁ-ゔゞ゛゜ー])")

    res = dict()

    for child in root.findall("entry", ns):
        orths = [orth.text for orth in child.findall("form/orth", ns) if orth is not None and orth.text]
        if not orths:
            continue

        hatsu = child.find("form/reading/hatsuon", ns).text
        hiras = "".join(hira_reg.findall(hatsu)).split("[Akz]")

        # There can be multiple accent values, first one seems to be default though.
        accent_elem = child.find("form/reading/accent", ns)
        if accent_elem is None:
            continue
        sub_accents = accent_elem.text.split("—")

        if len(sub_accents) == 1 and len(hiras) > 1:
            # Sometimes there's multiple accent patterns, but the default spans the whole reading
            hiras = ["".join(hiras)]
        elif len(sub_accents) != len(hiras):
            # Invalid config, should not happen
            raise Exception(f"Invalid accent config for {repr(orths)}: {repr(sub_accents)} / {repr(hiras)}")

        for orth in orths:
            if orth not in res:
                res[orth] = dict()
            hira_str = "-".join(hiras)
            if hira_str not in res[orth]:
                res[orth][hira_str] = "-".join(sub_accents)

    return res

def combine_data(data1, data2):
    res = data1.copy()
    for orth, hiras in data2.items():
        for hira, accent in hiras.items():
            if orth in res and hira in res[orth]:
                if accent != res[orth][hira]:
                    print(f"Found discrepancy for {orth}/{hira}: 10ten: {res[orth][hira]}, Wadoku: {accent}", file=sys.stderr)
                continue
            if orth not in res:
                res[orth] = dict()
            res[orth][hira] = accent
    return res

def print_data(data):
    comb_data = dict()
    for orth, hiras in data.items():
        if "|" in orth:
            raise Exception(f"Invalid character in orth {orth}")
        hira_slug = f'{"|".join(hiras.keys())},{"|".join(hiras.values())}'
        if hira_slug not in comb_data:
            comb_data[hira_slug] = []
        comb_data[hira_slug].append(orth)
    for hira_slug, orths in comb_data.items():
        orths_slug = "|".join(orths)
        if "," in orths_slug:
            print(f'"{orths_slug}",{hira_slug}')
        else:
            print(f'{orths_slug},{hira_slug}')

if __name__ == "__main__":
    print("Fetching 10ten...", file=sys.stderr)
    ten_data = fetch_10ten_data()
    print("Fetching Wadoku...", file=sys.stderr)
    wd_data = fetch_wadoku_data()
    print("Combining data...", file=sys.stderr)
    final_data = combine_data(ten_data, wd_data)
    print("Printing data...", file=sys.stderr)
    print_data(final_data)
