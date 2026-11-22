#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
mkdir -p "$root/build/gawk-5.4.0-hybrid"

RUSTBOX_TOOL_IMAGE=rustbox-gawk:2026-11-22 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    crate=/work/work/analysis/gawk-5.4.0/translations/c2rust-0.22.1/gawk-5.4.0-core-stable
    archive=$crate/target/release/libgawk_5_4_0_core.a
    extensions=/work/work/analysis/gawk-5.4.0/translations/c2rust-0.22.1/gawk-5.4.0-extensions/target/release
    output=/work/build/gawk-5.4.0-hybrid
    binary=$output/gawk
    canonical=/rustbox-gawk/normalized-clang
    residue=$output/c-residue

    cd "$crate"
    RUSTUP_TOOLCHAIN=1.99.0 cargo build --release --locked \
      >/work/work/analysis/gawk-5.4.0/translations/c2rust-0.22.1/core-cargo-hybrid.log 2>&1
    rm -rf "$residue"
    mkdir -p "$residue"
    cp "$canonical/support/pma.o" "$residue/pma.o"
    nm -g --defined-only "$residue/pma.o" >"$residue/pma.symbols"
    clang-18 -O2 -g -ffunction-sections -fdata-sections \
      -Wl,--gc-sections -Wl,-Map,"$binary.map" -o "$binary" \
      /work/bridges/gawk_main.c /work/bridges/grep_abi.c \
      "$residue/pma.o" "$archive" \
      -lreadline -lmpfr -lgmp -ldl -lpthread -lm
    ln -sfn gawk "$output/awk"

    rm -rf "$output/extension"
    mkdir -p "$output/extension/.libs"
    for name in filefuncs fnmatch fork inplace intdiv ordchr readdir readfile \
      revoutput revtwoway rwarray testext time; do
      cp "$extensions/lib$name.so" "$output/extension/.libs/$name.so"
    done
    cp "$binary" "$binary.stripped"
    strip --strip-all "$binary.stripped"
    cp "$canonical/gawk" "$output/gawk.canonical-stripped"
    strip --strip-all "$output/gawk.canonical-stripped"
    nm -g --defined-only "$archive" >"$output/gawk.archive-symbols"
    readelf -d "$binary" >"$output/gawk.dynamic"
    size -A "$binary" >"$output/gawk.sections"
    size -A "$output/gawk.canonical-stripped" >"$output/gawk.canonical-sections"
    "$binary" --version >"$output/version.out"
  '
