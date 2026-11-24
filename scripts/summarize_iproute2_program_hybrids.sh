#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-iproute2:2026-11-24 \
  exec "$root/scripts/run_tool.sh" python3 -B \
    /work/scripts/summarize_iproute2_program_hybrids.py \
    --repository /work \
    --hybrid-root /rustbox-iproute2/program-hybrids \
    --output /work/evidence/iproute2-7.3.0-program-hybrids.json
