#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-gzip:2026-11-21 \
  exec "$root/scripts/run_tool.sh" python3 /work/scripts/normalize_gzip.py \
    --repository /work \
    --output /rustbox-gzip/normalized-source \
    --manifest /work/work/analysis/gzip-1.14/normalized/normalization.json
