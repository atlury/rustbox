#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-inetutils:2026-11-23 \
  exec "$root/scripts/run_tool.sh" python3 -B \
    /work/scripts/summarize_inetutils_hybrids_02.py \
    --repository /work \
    --hybrid-root /rustbox-inetutils/program-hybrid \
    --output /work/evidence/inetutils-2.8-hybrid-small-02.json
