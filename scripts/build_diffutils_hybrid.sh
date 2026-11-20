#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
mkdir -p "$root/build/diffutils-3.12-hybrid"

RUSTBOX_TOOL_IMAGE=rustbox-diffutils:2026-11-20 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    archive=/work/work/analysis/diffutils-3.12/translations/c2rust-0.22.1/diffutils-3.12-stable/target/release/libdiffutils_3_12_normalized_audit.a
    output=/work/build/diffutils-3.12-hybrid
    canonical=/rustbox-diffutils/normalized-clang/src
    libraries="-ldl -lpthread -lm"

    for utility in cmp diff diff3 sdiff; do
      binary=$output/$utility-hybrid
      clang-18 -O2 -g -ffunction-sections -fdata-sections \
        -DRUSTBOX_ENTRY=rustbox_${utility}_main \
        -Wl,--gc-sections -Wl,-Map,"$binary.map" \
        -o "$binary" /work/bridges/diffutils_main.c "$archive" $libraries
      ln -sfn "$utility-hybrid" "$output/$utility"
      cp "$binary" "$binary.stripped"
      strip --strip-all "$binary.stripped"
      cp "$canonical/$utility" "$output/$utility.canonical-stripped"
      strip --strip-all "$output/$utility.canonical-stripped"
      size -A "$binary" > "$binary.sections"
      size -A "$output/$utility.canonical-stripped" > "$binary.canonical-sections"
      readelf -d "$binary" > "$binary.dynamic"
      sha256sum "$binary" "$binary.stripped" > "$binary.sha256"
    done
  '
