#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-findutils:2026-11-22 \
  exec "$root/scripts/run_tool.sh" python3 /work/scripts/summarize_findutils_oracle.py
