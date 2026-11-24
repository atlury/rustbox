#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-iproute2:2026-11-24 \
  exec "$root/scripts/run_tool.sh" python3 -B \
    /work/scripts/summarize_iproute2_multicall.py \
    --binary /rustbox-coreutils/canonical-clang-no-security-compdb/src/rustbox \
    --link-report /work/work/analysis/rustbox-multicall-link.json \
    --report-directory /work/work/analysis/iproute2-7.3.0/multicall \
    --output /work/evidence/iproute2-7.3.0-multicall.json
