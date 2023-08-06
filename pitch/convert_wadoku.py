#!/usr/bin/env python3
import xml.etree.ElementTree as ET
import sys, re

tree = ET.parse(sys.argv[1])
root = tree.getroot()

ns = {"": "http://www.wadoku.de/xml/entry"}
hira_reg = re.compile(r"(\[Akz\]|[ぁ-ゔゞ゛゜ー])")

for child in root.findall("entry", ns):
    orths = "|".join([orth.text for orth in child.findall("form/orth", ns) if orth is not None and orth.text])
    if not orths:
        continue

    hatsu = child.find("form/reading/hatsuon", ns).text
    hiras = "".join(hira_reg.findall(hatsu)).split("[Akz]")

    # There can be multiple accent values, first one seems to be default though.
    accent_elem = child.find("form/reading/accent", ns)
    if accent_elem is None:
        continue
    sub_accents = accent_elem.text.split("—")

    if len(sub_accents) == len(hiras):
        accents = "|".join(sub_accents)
        hira = "|".join(hiras)
    elif len(sub_accents) == 1:
        accents = sub_accents[0]
        hira = "".join(hiras)
    else:
        # Invalid config, should not happen
        raise Exception(f"Invalid accent config: {repr(sub_accents)} / {repr(hiras)}")

    print(f'"{orths}","{hira}","{accents}"')
