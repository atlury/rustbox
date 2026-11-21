#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-less:2026-11-22 \
  exec "$root/scripts/run_tool.sh" python3 /work/scripts/normalize_less.py \
    --repository /work --output /rustbox-less/normalized-source \
    --manifest /work/work/analysis/less-710/normalized/normalization.json
