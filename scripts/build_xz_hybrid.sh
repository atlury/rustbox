#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
mkdir -p "$root/build/xz-5.8.4-hybrid"

RUSTBOX_TOOL_IMAGE=rustbox-xz:2026-11-22 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    archive=/work/work/analysis/xz-5.8.4/translations/c2rust-0.22.1/xz-5.8.4-stable/target/release/libxz_5_8_4_normalized_audit.a
    output=/work/build/xz-5.8.4-hybrid
    canonical=/work/work/analysis/xz-5.8.4/normalized/clang-root/usr/bin
    binary=$output/xz

    rm -rf "$output"
    mkdir -p "$output"
    cp -R "$canonical/." "$output/"
    clang-18 -O2 -g -ffunction-sections -fdata-sections \
      -Wl,--gc-sections -Wl,-Map,"$binary.map" \
      -o "$binary" /work/bridges/xz_main.c "$archive" \
      -ldl -lpthread -lm
    for name in unxz xzcat lzma unlzma lzcat xzdec lzmadec lzmainfo; do
      ln -sf xz "$output/$name"
    done
    cp "$binary" "$binary.stripped"
    strip --strip-all "$binary.stripped"
    size -A "$binary" >"$binary.sections"
    readelf -d "$binary" >"$binary.dynamic"
    nm -g --defined-only "$binary" >"$binary.symbols"
    sha256sum "$binary" "$binary.stripped" >"$binary.sha256"
  '
