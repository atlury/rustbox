#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
python3 -B "$root/scripts/normalize_curl.py" \
  --repository "$root" \
  --output "$root/work/normalized/curl-8.23.0" \
  --manifest "$root/work/analysis/curl-8.23.0/normalization-manifest.json"
