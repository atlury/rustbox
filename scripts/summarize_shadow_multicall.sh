#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
exec python3 -B "$root/scripts/summarize_shadow_multicall.py" \
  --repository "$root" \
  --output "$root/evidence/shadow-4.20.4-multicall.json"
