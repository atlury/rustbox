#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-e2fsprogs:2026-11-24 \
  exec "$root/scripts/run_tool.sh" python3 /work/scripts/test_rustbox_multicall.py \
    --repository /work \
    --coreutils-build /rustbox-coreutils/canonical-clang-no-security-compdb \
    --util-linux-build /rustbox-util-linux/canonical-clang-compdb \
    --m4-oracle /rustbox-m4/normalized-clang/src/m4 \
    --pkgconf-oracle-dir /rustbox-pkgconf/normalized-clang-static \
    --file-oracle /rustbox-file/normalized-clang/src/file \
    --patch-oracle /rustbox-patch/normalized-clang/src/patch \
    --sed-oracle /rustbox-sed/normalized-clang/sed/sed \
    --diffutils-oracle-dir /rustbox-diffutils/normalized-clang/src \
    --grep-oracle /rustbox-grep/normalized-clang/src/grep \
    --gawk-oracle /rustbox-gawk/normalized-clang/gawk \
    --bc-oracle-dir /rustbox-bc/normalized-clang \
    --attr-oracle-dir /rustbox-attr/normalized-clang \
    --acl-oracle-dir /rustbox-acl/normalized-clang \
    --lz4-oracle-dir /work/work/analysis/lz4-1.11.1/normalized/clang \
    --less-oracle-dir /work/work/analysis/less-710/normalized/clang \
    --gzip-oracle-dir /rustbox-gzip/normalized-install-gcc/usr/bin \
    --xz-oracle-dir /work/work/analysis/xz-5.8.4/normalized/clang-root/usr/bin \
    --zstd-oracle-dir /rustbox-zstd/normalized-gcc/programs \
    --tar-oracle-root /work/work/analysis/tar-1.35/normalized/clang-root \
    --ncurses-oracle-root /work/work/analysis/ncurses-6.6/normalized/gcc-root \
    --findutils-oracle-root /rustbox-findutils/hybrid \
    --flex-oracle /rustbox-flex/normalized-gcc/src/flex \
    --curl-oracle /work/work/analysis/curl-8.23.0/oracle/curl-clang \
    --curl-config-oracle /work/work/analysis/curl-8.23.0/oracle/curl-config-clang \
    --inetutils-oracle-root /rustbox-inetutils/normalized-gcc \
    --kmod-oracle-root /rustbox-kmod/oracle-gcc \
    --procps-oracle-root /rustbox-procps/programs-gcc \
    --procps-oracle-library /rustbox-procps/oracle-gcc/library/.libs \
    --shadow-oracle-root /rustbox-shadow/programs-gcc \
    --rustbox /rustbox-coreutils/canonical-clang-no-security-compdb/src/rustbox \
    --output /work/work/analysis/rustbox-multicall-dispatch.json
