#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-gawk:2026-11-22 \
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
    --xz-report-directory /work/work/analysis/xz-5.8.4/multicall \
    --zstd-report-directory /work/work/analysis/zstd-1.5.7/multicall \
    --tar-report-directory /work/work/analysis/tar-1.35/multicall \
    --ncurses-report-directory /work/work/analysis/ncurses-6.6/multicall \
    --findutils-report-directory /work/work/analysis/findutils-4.10.0/multicall \
    --gawk-report-directory /work/work/analysis/gawk-5.4.0/multicall \
    --flex-report-directory /work/work/analysis/flex-2.6.4/multicall \
    --bison-report-directory /work/work/analysis/bison-3.8.2/multicall \
    --curl-report-directory /work/work/analysis/curl-8.23.0/multicall \
    --inetutils-report-directory /work/work/analysis/inetutils-2.8/multicall \
    --kmod-report-directory /work/work/analysis/kmod-34.3/multicall \
    --output /work/evidence/rustbox-multicall.json
