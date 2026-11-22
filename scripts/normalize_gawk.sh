#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-gawk:2026-11-22 \
  exec "$root/scripts/run_tool.sh" python3 /work/scripts/normalize_gawk.py \
    --repository /work \
    --output /rustbox-gawk/normalized-source \
    --manifest /work/work/analysis/gawk-5.4.0/normalization-manifest.json
