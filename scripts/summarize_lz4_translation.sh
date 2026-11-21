#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-lz4:2026-11-21 \
  exec "$root/scripts/run_tool.sh" python3 /work/scripts/summarize_lz4_translation.py \
    --repository /work --output /work/evidence/lz4-1.11.1-c2rust.json
