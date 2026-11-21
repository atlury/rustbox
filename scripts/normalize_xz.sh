#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-xz:2026-11-22 \
  exec "$root/scripts/run_tool.sh" python3 /work/scripts/normalize_xz.py \
    --repository /work \
    --output /rustbox-xz/normalized-source \
    --manifest /work/work/analysis/xz-5.8.4/normalized/normalization.json
