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
    for utility in gzip gunzip zcat uncompress zcmp zdiff zforce; do
      ln -s "$rustbox" "$dispatch/$utility"
    done

    python3 /work/tests/gzip-oracle-differential.py \
      --gcc-directory "$canonical" --clang-directory "$dispatch" \
      --applets gzip gunzip zcat uncompress zcmp zdiff zforce \
      --output "$output/differential.json"

    printf "alpha beta gamma\n%.0s" $(seq 1 2048) >"$output/input"
    printf "alpha delta gamma\n%.0s" $(seq 1 2048) >"$output/other"
    "$canonical/gzip" -n -9 -c "$output/input" >"$output/canonical.gz"
    "$canonical/gzip" -n -9 -c "$output/other" >"$output/other.gz"
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
    set +e
    valgrind --leak-check=full --show-leak-kinds=all \
      --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
      --log-file="$output/valgrind-zcmp.log" \
      "$rustbox" zcmp "$output/canonical.gz" "$output/other.gz" >/dev/null
    zcmp_status=$?
    valgrind --leak-check=full --show-leak-kinds=all \
      --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
      --log-file="$output/valgrind-zdiff.log" \
      "$rustbox" zdiff "$output/canonical.gz" "$output/other.gz" >/dev/null
    zdiff_status=$?
    set -e
    test "$zcmp_status" -eq 1
    test "$zdiff_status" -eq 1
    for operation in zcmp zdiff; do
      grep -q "ERROR SUMMARY: 0 errors" "$output/valgrind-$operation.log"
      grep -q "definitely lost: 0 bytes in 0 blocks" "$output/valgrind-$operation.log"
      grep -q "indirectly lost: 0 bytes in 0 blocks" "$output/valgrind-$operation.log"
      grep -q "possibly lost: 0 bytes in 0 blocks" "$output/valgrind-$operation.log"
    done
    cmp "$output/canonical.gz" "$output/multicall.gz"
    cmp "$output/input" "$output/multicall.out"
  '
