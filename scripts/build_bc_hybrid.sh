#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
mkdir -p "$root/build/bc-1.08.2-hybrid"

RUSTBOX_TOOL_IMAGE=rustbox-bc:2026-11-21 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    archive=/work/work/analysis/bc-1.08.2/translations/c2rust-0.22.1/bc-1.08.2-stable/target/release/libbc_1_08_2_normalized_audit.a
    output=/work/build/bc-1.08.2-hybrid
    canonical=/rustbox-bc/normalized-gcc

    for utility in bc dc; do
      binary=$output/$utility-hybrid
      clang-18 -O2 -g -ffunction-sections -fdata-sections \
        -DRUSTBOX_ENTRY=rustbox_${utility}_main \
        -Wl,--gc-sections -Wl,-Map,"$binary.map" \
        -o "$binary" /work/bridges/bc_main.c "$archive" \
        -ldl -lpthread -lm
      ln -sfn "$utility-hybrid" "$output/$utility"
      cp "$binary" "$binary.stripped"
      strip --strip-all "$binary.stripped"
      cp "$canonical/$utility/$utility" "$output/$utility.canonical-stripped"
      strip --strip-all "$output/$utility.canonical-stripped"
      size -A "$binary" > "$binary.sections"
      size -A "$output/$utility.canonical-stripped" > "$binary.canonical-sections"
      readelf -d "$binary" > "$binary.dynamic"
      sha256sum "$binary" "$binary.stripped" > "$binary.sha256"
    done
  '
