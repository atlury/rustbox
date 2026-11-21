#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-file:2026-11-20 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    output=/work/work/analysis/gzip-1.14/multicall
    rustbox=/rustbox-coreutils/canonical-clang-no-security-compdb/src/rustbox
    canonical=/rustbox-gzip/normalized-install-gcc/usr/bin
    dispatch=/rustbox-gzip/multicall-dispatch
    rm -rf "$output" "$dispatch"
    mkdir -p "$output" "$dispatch"
    for utility in gzip gunzip zcat uncompress; do
      ln -s "$rustbox" "$dispatch/$utility"
    done

    python3 /work/tests/gzip-oracle-differential.py \
      --gcc-directory "$canonical" --clang-directory "$dispatch" \
      --applets gzip gunzip zcat uncompress --output "$output/differential.json"

    printf "alpha beta gamma\n%.0s" $(seq 1 2048) >"$output/input"
    "$canonical/gzip" -n -9 -c "$output/input" >"$output/canonical.gz"
    valgrind --leak-check=full --show-leak-kinds=all \
      --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
      --log-file="$output/valgrind-compress.log" \
      "$rustbox" gzip -n -9 -c "$output/input" >"$output/multicall.gz"
    valgrind --leak-check=full --show-leak-kinds=all \
      --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
      --log-file="$output/valgrind-decompress.log" \
      "$rustbox" gzip -dc "$output/canonical.gz" >"$output/multicall.out"
    for operation in compress decompress; do
      grep -q "ERROR SUMMARY: 0 errors" "$output/valgrind-$operation.log"
      grep -q "All heap blocks were freed -- no leaks are possible" \
        "$output/valgrind-$operation.log"
    done
    cmp "$output/canonical.gz" "$output/multicall.gz"
    cmp "$output/input" "$output/multicall.out"
  '
