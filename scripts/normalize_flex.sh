#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
python3 -B "$root/scripts/normalize_flex.py" \
  --repository "$root" \
  --output "$root/work/normalized/flex-2.6.4" \
  --manifest "$root/work/analysis/flex-2.6.4/normalization-manifest.json"
