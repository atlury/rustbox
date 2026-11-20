#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
mkdir -p "$root/build/m4-1.4.21-hybrid"

RUSTBOX_TOOL_IMAGE=rustbox-normalize:2026-11-19 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    archive=/work/work/analysis/m4-1.4.21/translations/c2rust-0.22.1/m4-1.4.21-stable/target/release/libm4_1_4_21_normalized_audit.a
    support=/rustbox-m4/normalized-clang/lib/libm4.a
    output=/work/build/m4-1.4.21-hybrid/m4
    canonical=/rustbox-m4/normalized-clang/src/m4
    clang-18 -O2 -g -ffunction-sections -fdata-sections \
      -Wl,--gc-sections -Wl,-Map,"$output.map" \
      -o "$output" /work/bridges/m4_main.c "$archive" "$support" \
      -ldl -lpthread -lm
    cp "$output" "$output.stripped"
    strip --strip-all "$output.stripped"
    cp "$canonical" "$output.canonical-stripped"
    strip --strip-all "$output.canonical-stripped"
    size -A "$output" > "$output.sections"
    size -A "$output.canonical-stripped" > "$output.canonical-sections"
    readelf -d "$output" > "$output.dynamic"
    sha256sum "$output" "$output.stripped" > "$output.sha256"
  '
