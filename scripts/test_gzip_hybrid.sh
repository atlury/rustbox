#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-gzip:2026-11-21 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    hybrid=/work/build/gzip-1.14-hybrid
    canonical=/rustbox-gzip/normalized-install-gcc/usr/bin
    analysis=/work/work/analysis/gzip-1.14/hybrid
    rm -rf "$analysis"
    mkdir -p "$analysis"

    build=/rustbox-gzip/normalized-clang
    backup=$build/gzip.rustbox-backup
    cp "$build/gzip" "$backup"
    restore(){ mv -f "$backup" "$build/gzip"; }
    trap restore EXIT HUP INT TERM
    cp "$hybrid/gzip" "$build/gzip"
    if make -C "$build" -o gzip -j"$(nproc)" check \
        >"$analysis/upstream-tests.log" 2>&1
    then
      test_status=0
    else
      test_status=$?
    fi
    restore
    trap - EXIT HUP INT TERM
    cat "$analysis/upstream-tests.log"
    test "$test_status" -eq 0

    python3 /work/tests/gzip-oracle-differential.py \
      --gcc-directory "$canonical" --clang-directory "$hybrid" \
      --output "$analysis/differential.json"

    printf "alpha beta gamma\n%.0s" $(seq 1 2048) >"$analysis/input"
    "$canonical/gzip" -n -9 -c "$analysis/input" >"$analysis/canonical.gz"
    for implementation in canonical hybrid; do
      if test "$implementation" = canonical; then binary=$canonical/gzip; else binary=$hybrid/gzip; fi
      valgrind --leak-check=full --show-leak-kinds=all \
        --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
        --log-file="$analysis/valgrind-compress-$implementation.log" \
        "$binary" -n -9 -c "$analysis/input" >"$analysis/$implementation.gz"
      valgrind --leak-check=full --show-leak-kinds=all \
        --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
        --log-file="$analysis/valgrind-decompress-$implementation.log" \
        "$binary" -dc "$analysis/canonical.gz" >"$analysis/$implementation.out"
      grep -q "ERROR SUMMARY: 0 errors" "$analysis/valgrind-compress-$implementation.log"
      grep -q "ERROR SUMMARY: 0 errors" "$analysis/valgrind-decompress-$implementation.log"
      grep -q "All heap blocks were freed -- no leaks are possible" \
        "$analysis/valgrind-compress-$implementation.log"
      grep -q "All heap blocks were freed -- no leaks are possible" \
        "$analysis/valgrind-decompress-$implementation.log"
    done
    cmp "$analysis/canonical.gz" "$analysis/hybrid.gz"
    cmp "$analysis/canonical.out" "$analysis/hybrid.out"
  '
