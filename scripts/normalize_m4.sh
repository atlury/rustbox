#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-normalize:2026-11-19 \
  exec "$root/scripts/run_tool.sh" python3 /work/scripts/normalize_m4.py \
    --repository /work \
    --output /rustbox-m4/normalized-source \
    --manifest /work/work/analysis/m4-1.4.21/normalized/normalization.json
