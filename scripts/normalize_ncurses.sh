#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
exec python3 "$root/scripts/normalize_ncurses.py" \
  --repository "$root" \
  --output "$root/work/normalized/ncurses-6.6" \
  --manifest "$root/work/analysis/ncurses-6.6/normalization-manifest.json"
