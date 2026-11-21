#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
mkdir -p "$root/build/lz4-1.11.1-hybrid"

RUSTBOX_TOOL_IMAGE=rustbox-lz4:2026-11-21 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    archive=/work/work/analysis/lz4-1.11.1/translations/c2rust-0.22.1/lz4-1.11.1-stable/target/release/liblz4_1_11_1_normalized_audit.a
    output=/work/build/lz4-1.11.1-hybrid
    canonical=/work/work/analysis/lz4-1.11.1/normalized/gcc/lz4
    binary=$output/lz4

    clang-18 -O2 -g -ffunction-sections -fdata-sections \
      -Wl,--gc-sections -Wl,-Map,"$binary.map" \
      -o "$binary" /work/bridges/lz4_main.c "$archive" \
      -ldl -lpthread -lm
    for alias in lz4c lz4cat unlz4; do
      ln -sf lz4 "$output/$alias"
    done
    cp "$binary" "$binary.stripped"
    strip --strip-all "$binary.stripped"
    cp "$canonical" "$output/lz4.canonical-stripped"
    strip --strip-all "$output/lz4.canonical-stripped"
    size -A "$binary" > "$binary.sections"
    size -A "$output/lz4.canonical-stripped" > "$binary.canonical-sections"
    readelf -d "$binary" > "$binary.dynamic"
    sha256sum "$binary" "$binary.stripped" > "$binary.sha256"
  '
