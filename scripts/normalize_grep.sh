#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-grep:2026-11-21 \
  exec "$root/scripts/run_tool.sh" python3 /work/scripts/normalize_grep.py \
    --repository /work \
    --output /rustbox-grep/normalized-source \
    --manifest /work/work/analysis/grep-3.12/normalized/normalization.json
