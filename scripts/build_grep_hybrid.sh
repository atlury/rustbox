#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
mkdir -p "$root/build/grep-3.12-hybrid"

RUSTBOX_TOOL_IMAGE=rustbox-grep:2026-11-21 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    archive=/work/work/analysis/grep-3.12/translations/c2rust-0.22.1/grep-3.12-stable/target/release/libgrep_3_12_normalized_audit.a
    output=/work/build/grep-3.12-hybrid
    canonical=/rustbox-grep/normalized-clang/src/grep
    binary=$output/grep-hybrid

    clang-18 -O2 -g -ffunction-sections -fdata-sections \
      -Wl,--gc-sections -Wl,-Map,"$binary.map" \
      -o "$binary" /work/bridges/grep_main.c "$archive" \
      -lpcre2-8 -ldl -lpthread -lm
    ln -sfn grep-hybrid "$output/grep"
    cp "$binary" "$binary.stripped"
    strip --strip-all "$binary.stripped"
    cp "$canonical" "$output/grep.canonical-stripped"
    strip --strip-all "$output/grep.canonical-stripped"
    size -A "$binary" > "$binary.sections"
    size -A "$output/grep.canonical-stripped" > "$binary.canonical-sections"
    readelf -d "$binary" > "$binary.dynamic"
    sha256sum "$binary" "$binary.stripped" > "$binary.sha256"
  '
