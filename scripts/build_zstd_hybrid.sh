#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-zstd:2026-11-22 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    crate=/work/work/analysis/zstd-1.5.7/translations/c2rust-0.22.1/zstd-1.5.7-stable
    archive=$crate/target/release/libzstd_1_5_7_normalized_audit.a
    output=/rustbox-zstd/hybrid
    evidence=/work/work/analysis/zstd-1.5.7/hybrid
    artifacts=/work/work/analysis/zstd-1.5.7/hybrid-artifacts
    canonical=/work/work/analysis/zstd-1.5.7/normalized/clang-root/usr/bin
    source=/work/work/analysis/zstd-1.5.7/normalized/c2rust-source/programs
    rm -rf "$output" "$evidence" "$artifacts"
    mkdir -p "$output" "$evidence" "$artifacts"
    cd "$crate"
    cargo build --release
    cc -O2 -g -fno-omit-frame-pointer /work/bridges/zstd_main.c "$archive" \
      -ldl -lpthread -lm -lrt -lutil -o "$output/zstd"
    cp "$output/zstd" "$output/zstd.stripped"
    strip --strip-all "$output/zstd.stripped"
    readelf -d "$output/zstd" > "$evidence/zstd.dynamic"
    size -A "$output/zstd" > "$evidence/zstd.sections"
    nm -g --defined-only "$output/zstd" > "$evidence/zstd.symbols"
    cp "$output/zstd" "$output/zstd.stripped" "$artifacts/"
    for name in zstdmt unzstd zstdcat; do ln -s zstd "$output/$name"; done
    cp "$source/zstdgrep" "$source/zstdless" "$output/"
    chmod +x "$output/zstdgrep" "$output/zstdless"

    python3 /work/tests/zstd-oracle-differential.py \
      --gcc-directory "$canonical" \
      --clang-directory "$output" \
      --output "$evidence/differential.json"

    cd "$output"
    python3 -c "from pathlib import Path; Path(\"valgrind-input\").write_bytes((b\"translated zstd\\n\" * 4096) + bytes(range(256)))"
    cp valgrind-input valgrind-expected
    valgrind --leak-check=full --show-leak-kinds=all \
      --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
      --log-file="$evidence/valgrind-compress.log" \
      "$output/zstd" -T1 --keep --force valgrind-input
    valgrind --leak-check=full --show-leak-kinds=all \
      --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
      --log-file="$evidence/valgrind-decompress.log" \
      "$output/zstd" --decompress --keep --force valgrind-input.zst
    cmp valgrind-expected valgrind-input
    for operation in compress decompress; do
      grep -q "ERROR SUMMARY: 0 errors" "$evidence/valgrind-$operation.log"
      grep -q "definitely lost: 0 bytes in 0 blocks" "$evidence/valgrind-$operation.log"
      grep -q "indirectly lost: 0 bytes in 0 blocks" "$evidence/valgrind-$operation.log"
      grep -q "possibly lost: 0 bytes in 0 blocks" "$evidence/valgrind-$operation.log"
    done
  '
