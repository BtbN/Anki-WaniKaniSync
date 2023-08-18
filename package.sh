#!/bin/bash
cd "$(dirname "$0")"
rm -f ../anki-wanikanisync.ankiaddon
zip -r ../anki-wanikanisync.ankiaddon . -x "__pycache__/*" "**/__pycache__/*" ".git/*" ".gitignore" "./package.sh" "./meta.json" @
