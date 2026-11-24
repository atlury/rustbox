#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-iproute2:2026-11-24 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    base=/work/work/analysis/iproute2-7.3.0/program-closures
    python3 -B /work/scripts/summarize_iproute2_program_closures.py \
      --maps-directory "$base/maps" \
      --engines-directory "$base/engines" \
      --output "$base/summary.json"
    chmod a+rw "$base/summary.json"
  '
