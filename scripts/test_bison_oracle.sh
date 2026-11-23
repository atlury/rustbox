#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-bison:2026-11-23 \
  exec "$root/scripts/run_tool.sh" python3 -B \
    /work/tests/bison-oracle-differential.py \
    --gcc /work/work/analysis/bison-3.8.2/oracle/gcc-root/usr/bin/bison \
    --gcc-datadir /work/work/analysis/bison-3.8.2/oracle/gcc-root/usr/share/bison \
    --clang /work/work/analysis/bison-3.8.2/oracle/clang-root/usr/bin/bison \
    --clang-datadir /work/work/analysis/bison-3.8.2/oracle/clang-root/usr/share/bison \
    --source /work/work/upstream/bison-3.8.2 \
    --output /work/work/analysis/bison-3.8.2/oracle/differential.json
