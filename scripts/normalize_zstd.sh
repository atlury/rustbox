#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-zstd:2026-11-22 \
  exec "$root/scripts/run_tool.sh" python3 /work/scripts/normalize_zstd.py \
    --repository /work \
    --output /rustbox-zstd/normalized-source \
    --manifest /work/work/analysis/zstd-1.5.7/normalized/normalization.json
