#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
exec python3 -B "$root/scripts/summarize_e2fsprogs_script_frontends.py" \
  --directory "$root/work/analysis/e2fsprogs-1.47.4/script-frontends" \
  --output "$root/evidence/e2fsprogs-1.47.4-script-frontends.json"
