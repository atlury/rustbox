#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
exec python3 -B "$root/scripts/summarize_kmod_hybrid.py" \
  --repository "$root" --output "$root/evidence/kmod-34.3-hybrid.json"
