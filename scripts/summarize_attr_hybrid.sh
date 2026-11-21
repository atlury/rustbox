#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-attr:2026-11-21 \
  exec "$root/scripts/run_tool.sh" python3 /work/scripts/summarize_attr_hybrid.py \
    --repository /work --output /work/evidence/attr-2.6.0-hybrid.json
