#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-kmod:2026-11-24 \
  exec "$root/scripts/run_tool.sh" python3 \
    /work/scripts/summarize_kmod_multicall.py \
    --repository /work \
    --output /work/evidence/kmod-34.3-multicall.json
