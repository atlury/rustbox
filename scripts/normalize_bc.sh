#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-bc:2026-11-21 \
  exec "$root/scripts/run_tool.sh" python3 /work/scripts/normalize_bc.py \
    --repository /work \
    --output /rustbox-bc/normalized-source \
    --manifest /work/work/analysis/bc-1.08.2/normalized/normalization.json
