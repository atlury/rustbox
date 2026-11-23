#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-gawk:2026-11-22 \
  exec "$root/scripts/run_tool.sh" python3 /work/scripts/summarize_inetutils_multicall.py \
    --link-report /work/work/analysis/rustbox-multicall-link.json \
    --report-directory /work/work/analysis/inetutils-2.8/multicall \
    --output /work/evidence/inetutils-2.8-multicall.json
