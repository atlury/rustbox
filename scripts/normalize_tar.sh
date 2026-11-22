#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-tar:2026-11-22 \
  exec "$root/scripts/run_tool.sh" python3 /work/scripts/normalize_tar.py \
    --repository /work \
    --output /rustbox-tar/normalized-source \
    --manifest /work/work/analysis/tar-1.35/normalized/normalization.json
