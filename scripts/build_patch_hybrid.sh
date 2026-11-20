#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
mkdir -p "$root/build/patch-2.8-hybrid"

RUSTBOX_TOOL_IMAGE=rustbox-patch:2026-11-20 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    archive=/work/work/analysis/patch-2.8/translations/c2rust-0.22.1/patch-2.8-stable/target/release/libpatch_2_8_normalized_audit.a
    output=/work/build/patch-2.8-hybrid/patch-hybrid
    canonical=/rustbox-patch/normalized-clang/src/patch
    libraries="-lattr -ldl -lpthread -lm"

    clang-18 -O2 -g -ffunction-sections -fdata-sections \
      -Wl,--gc-sections -Wl,-Map,"$output.map" \
      -o "$output" /work/bridges/patch_main.c "$archive" $libraries
    ln -sfn patch-hybrid /work/build/patch-2.8-hybrid/patch
    cp "$output" "$output.stripped"
    strip --strip-all "$output.stripped"
    cp "$canonical" /work/build/patch-2.8-hybrid/patch.canonical-stripped
    strip --strip-all /work/build/patch-2.8-hybrid/patch.canonical-stripped
    size -A "$output" > "$output.sections"
    size -A /work/build/patch-2.8-hybrid/patch.canonical-stripped \
      > "$output.canonical-sections"
    readelf -d "$output" > "$output.dynamic"
    sha256sum "$output" "$output.stripped" > "$output.sha256"
  '
