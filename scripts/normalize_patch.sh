#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-patch:2026-11-20 \
  exec "$root/scripts/run_tool.sh" python3 /work/scripts/normalize_patch.py \
    --repository /work \
    --output /rustbox-patch/normalized-source \
    --manifest /work/work/analysis/patch-2.8/normalized/normalization.json
