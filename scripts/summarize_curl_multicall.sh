#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-curl:2026-11-23 \
  exec "$root/scripts/run_tool.sh" python3 /work/scripts/summarize_curl_multicall.py \
    --binary /rustbox-coreutils/canonical-clang-no-security-compdb/src/rustbox \
    --link-report /work/work/analysis/rustbox-multicall-link.json \
    --report-directory /work/work/analysis/curl-8.23.0/multicall \
    --hybrid-evidence /work/evidence/curl-8.23.0-hybrid.json \
    --output /work/evidence/curl-8.23.0-multicall.json
