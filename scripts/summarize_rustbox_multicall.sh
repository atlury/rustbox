#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-normalize:2026-11-19 \
  exec "$root/scripts/run_tool.sh" python3 /work/scripts/summarize_rustbox_multicall.py \
    --binary /rustbox-coreutils/canonical-clang-no-security-compdb/src/rustbox \
    --link-report /work/work/analysis/rustbox-multicall-link.json \
    --dispatch-report /work/work/analysis/rustbox-multicall-dispatch.json \
    --differential-report /work/work/analysis/rustbox-multicall-differential.json \
    --m4-report-directory /work/work/analysis/m4-1.4.21/multicall \
    --pkgconf-report-directory /work/work/analysis/pkgconf-3.0.11/multicall \
    --output /work/evidence/rustbox-multicall.json
