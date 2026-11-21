#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-file:2026-11-20 \
  exec "$root/scripts/run_tool.sh" python3 /work/scripts/summarize_rustbox_multicall.py \
    --binary /rustbox-coreutils/canonical-clang-no-security-compdb/src/rustbox \
    --link-report /work/work/analysis/rustbox-multicall-link.json \
    --dispatch-report /work/work/analysis/rustbox-multicall-dispatch.json \
    --differential-report /work/work/analysis/rustbox-multicall-differential.json \
    --m4-report-directory /work/work/analysis/m4-1.4.21/multicall \
    --pkgconf-report-directory /work/work/analysis/pkgconf-3.0.11/multicall \
    --file-report-directory /work/work/analysis/file-5.48/multicall \
    --patch-report-directory /work/work/analysis/patch-2.8/multicall \
    --sed-report-directory /work/work/analysis/sed-4.10/multicall \
    --diffutils-report-directory /work/work/analysis/diffutils-3.12/multicall \
    --grep-report-directory /work/work/analysis/grep-3.12/multicall \
    --bc-report-directory /work/work/analysis/bc-1.08.2/multicall \
    --attr-report-directory /work/work/analysis/attr-2.6.0/multicall \
    --acl-report-directory /work/work/analysis/acl-2.4.0/multicall \
    --lz4-report-directory /work/work/analysis/lz4-1.11.1/multicall \
    --less-report-directory /work/work/analysis/less-710/multicall \
    --gzip-report-directory /work/work/analysis/gzip-1.14/multicall \
    --output /work/evidence/rustbox-multicall.json
