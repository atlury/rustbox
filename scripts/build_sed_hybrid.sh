#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
mkdir -p "$root/build/sed-4.10-hybrid"

RUSTBOX_TOOL_IMAGE=rustbox-sed:2026-11-20 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    archive=/work/work/analysis/sed-4.10/translations/c2rust-0.22.1/sed-4.10-stable/target/release/libsed_4_10_normalized_audit.a
    output=/work/build/sed-4.10-hybrid/sed-hybrid
    canonical=/rustbox-sed/normalized-clang/sed/sed
    libraries="-lacl -lattr -ldl -lpthread -lm"

    clang-18 -O2 -g -ffunction-sections -fdata-sections \
      -Wl,--gc-sections -Wl,-Map,"$output.map" \
      -o "$output" /work/bridges/sed_main.c "$archive" $libraries
    ln -sfn sed-hybrid /work/build/sed-4.10-hybrid/sed
    cp "$output" "$output.stripped"
    strip --strip-all "$output.stripped"
    cp "$canonical" /work/build/sed-4.10-hybrid/sed.canonical-stripped
    strip --strip-all /work/build/sed-4.10-hybrid/sed.canonical-stripped
    size -A "$output" > "$output.sections"
    size -A /work/build/sed-4.10-hybrid/sed.canonical-stripped \
      > "$output.canonical-sections"
    readelf -d "$output" > "$output.dynamic"
    sha256sum "$output" "$output.stripped" > "$output.sha256"
  '
