#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
mkdir -p "$root/build/gzip-1.14-hybrid"

RUSTBOX_TOOL_IMAGE=rustbox-gzip:2026-11-21 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    archive=/work/work/analysis/gzip-1.14/translations/c2rust-0.22.1/gzip-1.14-stable/target/release/libgzip_1_14_reachable_audit.a
    support=/rustbox-gzip/normalized-clang/lib/libgzip.a
    output=/work/build/gzip-1.14-hybrid
    canonical=/rustbox-gzip/normalized-install-gcc/usr/bin
    binary=$output/gzip

    rm -rf "$output"
    mkdir -p "$output"
    cp -R "$canonical/." "$output/"
    clang-18 -O2 -g -ffunction-sections -fdata-sections \
      -Wl,--gc-sections -Wl,-Map,"$binary.map" \
      -o "$binary" /work/bridges/gzip_main.c "$archive" "$support" \
      -ldl -lpthread -lm
    cp "$binary" "$binary.stripped"
    strip --strip-all "$binary.stripped"
    cp /work/work/analysis/gzip-1.14/normalized/gzip-gcc \
      "$output/gzip.canonical-stripped"
    strip --strip-all "$output/gzip.canonical-stripped"
    size -A "$binary" >"$binary.sections"
    size -A "$output/gzip.canonical-stripped" >"$binary.canonical-sections"
    readelf -d "$binary" >"$binary.dynamic"
    nm -g --defined-only "$binary" >"$binary.symbols"
    sha256sum "$binary" "$binary.stripped" >"$binary.sha256"
  '
