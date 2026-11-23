#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-procps:2026-11-24 \
  exec "$root/scripts/run_tool.sh" python3 -B \
    /work/scripts/summarize_procps_normalization.py \
    --repository /work \
    --gcc-root /rustbox-procps/normalized-programs-gcc \
    --clang-root /rustbox-procps/normalized-programs-clang-18 \
    --output /work/evidence/procps-ng-4.0.7-normalization.json
