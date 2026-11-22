#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
exec python3 "$root/scripts/summarize_ncurses_normalization.py" \
  --repository "$root" --output "$root/evidence/ncurses-6.6-normalization.json"
