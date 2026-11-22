#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-flex:2026-11-22 \
  exec "$root/scripts/run_tool.sh" python3 -B /work/scripts/summarize_flex_oracle.py
