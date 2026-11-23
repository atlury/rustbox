#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
python3 -B "$root/scripts/normalize_bison.py" \
  --repository "$root" \
  --output "$root/work/normalized/bison-3.8.2" \
  --manifest "$root/work/analysis/bison-3.8.2/normalization-manifest.json"
