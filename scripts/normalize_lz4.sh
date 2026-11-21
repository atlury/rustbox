#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-lz4:2026-11-21 \
  exec "$root/scripts/run_tool.sh" python3 /work/scripts/normalize_lz4.py \
    --repository /work \
    --output /rustbox-lz4/normalized-source \
    --manifest /work/work/analysis/lz4-1.11.1/normalized/normalization.json
