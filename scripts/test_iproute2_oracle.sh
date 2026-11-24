#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-iproute2:2026-11-24 \
  exec "$root/scripts/run_tool.sh" python3 \
    /work/tests/iproute2-oracle-differential.py \
    --gcc-root /rustbox-iproute2/programs-gcc \
    --clang-root /rustbox-iproute2/programs-clang-18 \
    --output /work/work/analysis/iproute2-7.3.0/oracle/differential.json
