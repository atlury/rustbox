#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-zstd:2026-11-22 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    source=/work/work/analysis/zstd-1.5.7/normalized/c2rust-source
    output=/work/work/analysis/zstd-1.5.7/translation-portable
    oracle=/work/work/analysis/zstd-1.5.7/normalized/clang-root/usr/bin
    root=$output/root
    feature_flags="HAVE_ZLIB=0 HAVE_LZMA=0 HAVE_LZ4=0 BACKTRACE=0 ZSTD_NO_ASM=1"
    portable_flags="-DDYNAMIC_BMI2=0 -DZSTD_NO_INTRINSICS=1 -DXXH_VECTOR=0 -DXXH_DEBUGLEVEL=1"

    case "$output" in /work/work/analysis/zstd-1.5.7/*) ;; *) exit 2 ;; esac
    rm -rf "$output"
    mkdir -p "$output"
    cd "$source"
    make clean
    make -j"$(nproc)" zstd-release CC=clang-18 MOREFLAGS="$portable_flags" $feature_flags
    make -C programs install PREFIX=/usr DESTDIR="$root" CC=clang-18 \
      MOREFLAGS="$portable_flags" $feature_flags
    python3 /work/tests/zstd-oracle-differential.py \
      --gcc-directory "$oracle" \
      --clang-directory "$root/usr/bin" \
      --output "$output/canonical-normalized-differential.json"
  '
