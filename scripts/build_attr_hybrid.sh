#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
mkdir -p "$root/build/attr-2.6.0-hybrid"

RUSTBOX_TOOL_IMAGE=rustbox-attr:2026-11-21 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    archive=/work/work/analysis/attr-2.6.0/translations/c2rust-0.22.1/attr-2.6.0-stable/target/release/libattr_2_6_0_normalized_audit.a
    output=/work/build/attr-2.6.0-hybrid
    canonical=/rustbox-attr/normalized-gcc

    for utility in attr getfattr setfattr; do
      binary=$output/$utility-hybrid
      clang-18 -O2 -g -ffunction-sections -fdata-sections \
        -DRUSTBOX_ENTRY=rustbox_${utility}_main \
        -Wl,--gc-sections -Wl,-Map,"$binary.map" \
        -o "$binary" /work/bridges/attr_main.c "$archive" \
        -ldl -lpthread -lm
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
