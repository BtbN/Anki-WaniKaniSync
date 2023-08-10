#!/usr/bin/env python3
import requests
import json

s = requests.Session()
res = s.get("https://data.10ten.study/jpdict/reader/version-en.json")
res.raise_for_status()
version_info = res.json()

major = "2"
minor = version_info["words"][major]["minor"]
patch = version_info["words"][major]["patch"]
parts = version_info["words"][major]["parts"]

# format from: https://github.com/birchill/jpdict-idb/blob/main/src/words.ts
for part in range(1, parts + 1):
    res = s.get(f"https://data.10ten.study/jpdict/reader/words/en/{major}.{minor}.{patch}-{part}.jsonl")
    res.raise_for_status()
    for line in res.iter_lines():
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

        ks = "|".join(k)
        rs = "|".join(rn)
        rms = "|".join(rmn)

        print(f'"{ks}","{rs}",{rms}')
