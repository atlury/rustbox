#!/bin/sh
# SPDX-License-Identifier: BSD-2-Clause
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-file:2026-11-20 \
  exec "$root/scripts/run_tool.sh" python3 /work/scripts/normalize_file.py \
    --repository /work \
    --output /rustbox-file/normalized-source \
    --manifest /work/work/analysis/file-5.48/normalized/normalization.json
