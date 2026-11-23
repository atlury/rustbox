#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
python3 -B "$root/scripts/summarize_curl_translation.py" \
  --repository "$root" \
  --output "$root/evidence/curl-8.23.0-c2rust.json"
