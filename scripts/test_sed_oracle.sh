#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-sed:2026-11-20 \
  exec "$root/scripts/run_tool.sh" python3 /work/tests/sed-oracle-differential.py \
    --gcc /rustbox-sed/oracle-gcc/sed/sed \
    --clang /rustbox-sed/oracle-clang/sed/sed \
    --output /work/work/analysis/sed-4.10/oracle/differential.json

