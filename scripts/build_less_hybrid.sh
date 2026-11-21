#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
mkdir -p "$root/build/less-710-hybrid"

RUSTBOX_TOOL_IMAGE=rustbox-less:2026-11-22 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    archive=/work/work/analysis/less-710/translations/c2rust-0.22.1/less-710-stable/target/release/libless_710_normalized_audit.a
    output=/work/build/less-710-hybrid
    canonical=/work/work/analysis/less-710/normalized/gcc/less
    binary=$output/less

    clang-18 -O2 -g -ffunction-sections -fdata-sections \
      -Wl,--gc-sections -Wl,-Map,"$binary.map" \
      -o "$binary" /work/bridges/less_main.c "$archive" \
      -ltinfo -ldl -lpthread -lm
    ln -sf less "$output/lessecho"
    cp "$binary" "$binary.stripped"
    strip --strip-all "$binary.stripped"
    cp "$canonical" "$output/less.canonical-stripped"
    strip --strip-all "$output/less.canonical-stripped"
    size -A "$binary" > "$binary.sections"
    size -A "$output/less.canonical-stripped" > "$binary.canonical-sections"
    readelf -d "$binary" > "$binary.dynamic"
    sha256sum "$binary" "$binary.stripped" > "$binary.sha256"
  '
