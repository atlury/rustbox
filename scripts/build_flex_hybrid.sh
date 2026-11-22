#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
mkdir -p "$root/build/flex-2.6.4-hybrid"

RUSTBOX_TOOL_IMAGE=rustbox-flex:2026-11-22 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    crate=/work/work/analysis/flex-2.6.4/translations/c2rust-0.22.1/flex-2.6.4-stable
    archive=$crate/target/release/libflex_2_6_4_normalized_audit.a
    output=/work/build/flex-2.6.4-hybrid
    binary=$output/flex
    cd "$crate"
    cargo build --release >cargo-hybrid.log 2>&1
    clang-18 -O2 -g -ffunction-sections -fdata-sections \
      -Wl,--gc-sections -Wl,-Map,"$binary.map" \
      -o "$binary" /work/bridges/flex_main.c "$archive" \
      -ldl -lpthread -lm
    ln -sf flex "$output/flex++"
    ln -sf flex "$output/lex"
    test "$(nm -g --defined-only "$binary" | grep -c " rustbox_flex_main$")" -eq 1
    test "$(nm -g --defined-only "$binary" | grep -c " rustbox_flexpp_main$")" -eq 1
    test "$(nm -g --defined-only "$binary" | grep -c " rustbox_lex_main$")" -eq 1
    cp "$binary" "$binary.stripped"
    strip --strip-all "$binary.stripped"
    size -A "$binary" >"$binary.sections"
    readelf -d "$binary" >"$binary.dynamic"
    sha256sum "$binary" "$binary.stripped" >"$binary.sha256"
  '
