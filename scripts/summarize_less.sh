#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
"$root/scripts/summarize_less_translation.py" \
  --repository "$root" --output "$root/evidence/less-710-c2rust.json"
"$root/scripts/summarize_less_hybrid.py" \
  --repository "$root" --output "$root/evidence/less-710-hybrid.json"
