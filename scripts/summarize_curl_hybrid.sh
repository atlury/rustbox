#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
python3 -B "$root/scripts/summarize_curl_hybrid.py" \
  --repository "$root" \
  --output "$root/evidence/curl-8.23.0-hybrid.json"
