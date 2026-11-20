#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-sed:2026-11-20 \
  exec "$root/scripts/run_tool.sh" python3 /work/scripts/normalize_sed.py \
    --repository /work \
    --output /rustbox-sed/normalized-source \
    --manifest /work/work/analysis/sed-4.10/normalized/normalization.json

