#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-shadow:2026-11-24 \
  exec "$root/scripts/run_tool.sh" \
    python3 /work/tests/shadow-oracle-differential.py \
      --gcc-root /rustbox-shadow/programs-gcc \
      --clang-root /rustbox-shadow/programs-clang-18 \
      --output /work/work/analysis/shadow-4.20.4/oracle/differential.json
