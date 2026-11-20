#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-diffutils:2026-11-20 \
  exec "$root/scripts/run_tool.sh" python3 /work/scripts/normalize_diffutils.py \
    --repository /work \
    --output /rustbox-diffutils/normalized-source \
    --manifest /work/work/analysis/diffutils-3.12/normalized/normalization.json
