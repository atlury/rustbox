#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-xz:2026-11-22 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    source=/work/work/analysis/xz-5.8.4/normalized/c2rust-source
    output=/work/work/analysis/xz-5.8.4/translation-portable
    root=$output/root
    log=$output/check.log

    case "$output" in /work/work/analysis/xz-5.8.4/*) ;; *) exit 2 ;; esac
    rm -rf "$output"
    mkdir -p "$output"
    cd "$source"
    make clean
    make -j"$(nproc)"
    if make -j"$(nproc)" check >"$log" 2>&1; then
      cat "$log"
    else
      status=$?
      cat "$log"
      exit "$status"
    fi
    make DESTDIR="$root" install
    python3 /work/tests/xz-oracle-differential.py \
      --gcc-directory /work/work/analysis/xz-5.8.4/normalized/clang-root/usr/bin \
      --clang-directory "$root/usr/bin" \
      --output "$output/canonical-normalized-differential.json"
  '
