#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
exec "$root/scripts/run_multicall_tool.sh" sh -eu -c '
    output=/work/work/analysis/grep-3.12/multicall
    rustbox=/rustbox-coreutils/canonical-clang-no-security-compdb/src/rustbox
    canonical=/rustbox-grep/normalized-gcc/src/grep
    build=/rustbox-grep/normalized-gcc
    rm -rf "$output"
    mkdir -p "$output"

    cd "$build"
    make -j"$(nproc)" all > "$output/pretest-build.log" 2>&1
    chown -R nobody:nogroup "$build"

    python3 /work/tests/grep-oracle-differential.py \
      --gcc "$canonical" --clang "$rustbox" \
      --output "$output/differential.json"
    python3 /work/tests/grep-alias-differential.py \
      --canonical-directory "$build/src" --rustbox "$rustbox" \
      --output "$output/alias-differential.json"

    installed=$build/src/grep
    saved=$installed.rustbox-canonical
    restore()
    {
      if test -e "$saved"; then
        rm -f "$installed"
        mv "$saved" "$installed"
      fi
    }
    trap restore EXIT HUP INT TERM
    test ! -e "$saved"
    mv "$installed" "$saved"
    ln -s "$rustbox" "$installed"
    find "$build/tests" "$build/gnulib-tests" -type f \
      \( -name "*.log" -o -name "*.trs" \) -delete
    runuser --user=nobody -- make -C "$build/tests" -j"$(nproc)" check \
      > "$output/upstream-tests.log" 2>&1
    runuser --user=nobody -- make -C "$build/gnulib-tests" -j"$(nproc)" check \
      >> "$output/upstream-tests.log" 2>&1
    restore
    trap - EXIT HUP INT TERM

    printf "alpha\nbeta\ngamma\n" > "$output/input"
    status=0
    valgrind --leak-check=full --show-leak-kinds=all \
      --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
      --log-file="$output/valgrind.log" \
      "$rustbox" grep -n -E "alpha|gamma" "$output/input" \
      > "$output/valgrind.out" || status=$?
    test "$status" -eq 99
    grep -q "ERROR SUMMARY: 3 errors" "$output/valgrind.log"
    grep -q "definitely lost: 0 bytes in 0 blocks" "$output/valgrind.log"
    grep -q "indirectly lost: 0 bytes in 0 blocks" "$output/valgrind.log"
    grep -q "possibly lost: 18,688 bytes in 11 blocks" "$output/valgrind.log"
    grep -q "still reachable: 119,466 bytes in 39 blocks" "$output/valgrind.log"
  '
