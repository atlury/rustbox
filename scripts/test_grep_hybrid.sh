#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
"$root/scripts/build_grep_hybrid.sh"

RUSTBOX_TOOL_IMAGE=rustbox-grep:2026-11-21 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    output=/work/work/analysis/grep-3.12/hybrid
    hybrids=/work/build/grep-3.12-hybrid
    canonical=/rustbox-grep/normalized-gcc/src/grep
    build=/rustbox-grep/normalized-gcc
    rm -rf "$output"
    mkdir -p "$output"

    cd "$build"
    make -j"$(nproc)" all > "$output/pretest-build.log" 2>&1
    chown -R nobody:nogroup "$build"

    python3 /work/tests/grep-oracle-differential.py \
      --gcc "$canonical" --clang "$hybrids/grep-hybrid" \
      --output "$output/differential.json"

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
    ln -s "$hybrids/grep-hybrid" "$installed"
    find "$build/tests" "$build/gnulib-tests" -type f \
      \( -name "*.log" -o -name "*.trs" \) -delete
    runuser --user=nobody -- make -C "$build/tests" -j"$(nproc)" check \
      > "$output/upstream-tests.log" 2>&1
    runuser --user=nobody -- make -C "$build/gnulib-tests" -j"$(nproc)" check \
      >> "$output/upstream-tests.log" 2>&1
    restore
    trap - EXIT HUP INT TERM

    printf "alpha\nbeta\ngamma\n" > "$output/input"
    for implementation in hybrid canonical; do
      case $implementation in
        hybrid) binary=$hybrids/grep-hybrid ;;
        canonical) binary=$canonical ;;
      esac
      status=0
      valgrind --leak-check=full --show-leak-kinds=all \
        --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
        --log-file="$output/valgrind-$implementation.log" \
        "$binary" -n -E "alpha|gamma" "$output/input" \
        > "$output/valgrind-$implementation.out" || status=$?
      test "$status" -eq 99
      sed -n "/HEAP SUMMARY/,+2p" "$output/valgrind-$implementation.log" \
        | sed "s/^==[0-9]*== *//" > "$output/valgrind-$implementation-heap"
    done
    cmp "$output/valgrind-canonical.out" "$output/valgrind-hybrid.out"
    cmp "$output/valgrind-canonical-heap" "$output/valgrind-hybrid-heap"
    for implementation in hybrid canonical; do
      log=$output/valgrind-$implementation.log
      grep -q "ERROR SUMMARY: 3 errors" "$log"
      grep -q "definitely lost: 0 bytes in 0 blocks" "$log"
      grep -q "indirectly lost: 0 bytes in 0 blocks" "$log"
      grep -q "possibly lost: 18,688 bytes in 11 blocks" "$log"
      grep -q "still reachable: 119,466 bytes in 39 blocks" "$log"
    done
  '
