#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-attr:2026-11-21 \
  exec "$root/scripts/run_tool.sh" python3 /work/scripts/normalize_attr.py \
    --repository /work \
    --output /rustbox-attr/normalized-source \
    --manifest /work/work/analysis/attr-2.6.0/normalized/normalization.json
