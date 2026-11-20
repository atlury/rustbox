#!/bin/sh
# SPDX-License-Identifier: BSD-2-Clause
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
mkdir -p "$root/build/file-5.48-hybrid"

RUSTBOX_TOOL_IMAGE=rustbox-file:2026-11-20 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    archive=/work/work/analysis/file-5.48/translations/c2rust-0.22.1/file-5.48-stable/target/release/libfile_5_48_normalized_audit.a
    output=/work/build/file-5.48-hybrid/file-hybrid
    canonical=/rustbox-file/normalized-clang/src/file
    libraries="-lbz2 -llz -llzma -lseccomp -lz -lzstd -ldl -lpthread -lm"

    clang-18 -O2 -g -ffunction-sections -fdata-sections \
      -Wl,--gc-sections -Wl,-Map,"$output.map" \
      -o "$output" /work/bridges/file_main.c "$archive" $libraries
    ln -sfn file-hybrid /work/build/file-5.48-hybrid/file
    cp "$output" "$output.stripped"
    strip --strip-all "$output.stripped"
    cp "$canonical" /work/build/file-5.48-hybrid/file.canonical-stripped
    strip --strip-all /work/build/file-5.48-hybrid/file.canonical-stripped
    size -A "$output" > "$output.sections"
    size -A /work/build/file-5.48-hybrid/file.canonical-stripped \
      > "$output.canonical-sections"
    readelf -d "$output" > "$output.dynamic"
    sha256sum "$output" "$output.stripped" > "$output.sha256"
  '
