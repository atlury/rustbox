#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-normalize:2026-11-19 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    source=/work/work/upstream/zlib-1.4
    analysis=/work/work/analysis/zlib-1.4
    output=$analysis/rust-tests
    canonical=$analysis/canonical-gcc-cmake/libz.a
    rust=$analysis/translations/c2rust-0.22.1/zlib-1.4-stable/target/release/libzlib_1_4_normalized_audit.a
    mkdir -p "$output"
    for program in example infcover minigzip; do
      gcc -O2 -I"$source" "$source/test/$program.c" "$canonical" \
        -ldl -lpthread -lm -o "$output/canonical-$program"
      gcc -O2 -I"$source" "$source/test/$program.c" "$rust" \
        -ldl -lpthread -lm -o "$output/rust-$program"
    done
    python3 /work/tests/zlib-rust-differential.py \
      --canonical-example "$output/canonical-example" \
      --rust-example "$output/rust-example" \
      --canonical-infcover "$output/canonical-infcover" \
      --rust-infcover "$output/rust-infcover" \
      --canonical-minigzip "$output/canonical-minigzip" \
      --rust-minigzip "$output/rust-minigzip" \
      --rust-library "$rust" \
      --output "$analysis/translations/c2rust-0.22.1/zlib-1.4-stable/differential.json"
  '
