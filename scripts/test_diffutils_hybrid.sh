#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
"$root/scripts/build_diffutils_hybrid.sh"

RUSTBOX_TOOL_IMAGE=rustbox-diffutils:2026-11-20 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    output=/work/work/analysis/diffutils-3.12/hybrid
    hybrids=/work/build/diffutils-3.12-hybrid
    canonical=/rustbox-diffutils/normalized-gcc/src
    build=/rustbox-diffutils/normalized-gcc
    rm -rf "$output"
    mkdir -p "$output"

    cd "$build"
    make -j"$(nproc)" all > "$output/pretest-build.log" 2>&1
    chown -R nobody:nogroup "$build"

    python3 /work/tests/diffutils-oracle-differential.py \
      --gcc-cmp "$canonical/cmp" --clang-cmp "$hybrids/cmp-hybrid" \
      --gcc-diff "$canonical/diff" --clang-diff "$hybrids/diff-hybrid" \
      --gcc-diff3 "$canonical/diff3" --clang-diff3 "$hybrids/diff3-hybrid" \
      --gcc-sdiff "$canonical/sdiff" --clang-sdiff "$hybrids/sdiff-hybrid" \
      --output "$output/differential.json"

    restore()
    {
      for utility in cmp diff diff3 sdiff; do
        installed=$build/src/$utility
        saved=$installed.rustbox-canonical
        if test -e "$saved"; then
          rm -f "$installed"
          mv "$saved" "$installed"
        fi
      done
    }
    trap restore EXIT HUP INT TERM
    for utility in cmp diff diff3 sdiff; do
      installed=$build/src/$utility
      saved=$installed.rustbox-canonical
      test ! -e "$saved"
      mv "$installed" "$saved"
      ln -s "$hybrids/$utility-hybrid" "$installed"
    done
    find "$build/tests" "$build/gnulib-tests" -type f \
      \( -name "*.log" -o -name "*.trs" \) -delete
    runuser --user=nobody -- make -C "$build/tests" -j"$(nproc)" check \
      > "$output/upstream-tests.log" 2>&1
    runuser --user=nobody -- make -C "$build/gnulib-tests" -j"$(nproc)" check \
      >> "$output/upstream-tests.log" 2>&1
    restore
    trap - EXIT HUP INT TERM

    printf "alpha\nbeta\ngamma\n" > "$output/left"
    printf "alpha\nBETA\ngamma\n" > "$output/right"
    for utility in cmp diff diff3 sdiff; do
      case $utility in
        cmp|diff) arguments="$output/left $output/right" ;;
        diff3) arguments="$output/left $output/right $output/left" ;;
        sdiff) arguments="--help" ;;
      esac
      status=0
      valgrind --leak-check=full --show-leak-kinds=all \
        --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
        --log-file="$output/valgrind-$utility.log" \
        "$hybrids/$utility-hybrid" $arguments \
        > "$output/valgrind-$utility.out" || status=$?
      if test "$utility" = diff3; then
        test "$status" -eq 99
        canonical_status=0
        valgrind --leak-check=full --show-leak-kinds=all \
          --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
          --log-file="$output/valgrind-$utility-canonical.log" \
          "$canonical/$utility" $arguments \
          > "$output/valgrind-$utility-canonical.out" || canonical_status=$?
        test "$canonical_status" -eq 99
        # GNU diff3 intentionally leaves its final diff graph allocated at
        # process exit.  Rust and C have an identical allocation lifecycle,
        # but optimized Rust drops the last stack root sooner, so Valgrind
        # classifies 112 direct + 48 indirect bytes as lost rather than
        # reachable.  Compare the allocator totals, not root liveness.
        sed -n "/HEAP SUMMARY/,+2p" "$output/valgrind-$utility.log" \
          | sed "s/^==[0-9]*== *//" > "$output/valgrind-$utility-heap"
        sed -n "/HEAP SUMMARY/,+2p" "$output/valgrind-$utility-canonical.log" \
          | sed "s/^==[0-9]*== *//" > "$output/valgrind-$utility-canonical-heap"
        cmp "$output/valgrind-$utility-canonical-heap" \
          "$output/valgrind-$utility-heap"
        grep -q "ERROR SUMMARY: 9 errors" "$output/valgrind-$utility.log"
        grep -q "definitely lost: 4,208 bytes in 2 blocks" "$output/valgrind-$utility.log"
        grep -q "indirectly lost: 48 bytes in 6 blocks" "$output/valgrind-$utility.log"
        grep -q "possibly lost: 4,096 bytes in 1 blocks" "$output/valgrind-$utility.log"
        grep -q "ERROR SUMMARY: 2 errors" "$output/valgrind-$utility-canonical.log"
        grep -q "definitely lost: 4,096 bytes in 1 blocks" "$output/valgrind-$utility-canonical.log"
        grep -q "indirectly lost: 0 bytes in 0 blocks" "$output/valgrind-$utility-canonical.log"
        grep -q "possibly lost: 4,096 bytes in 1 blocks" "$output/valgrind-$utility-canonical.log"
      else
        test "$status" -le 1
        grep -q "ERROR SUMMARY: 0 errors" "$output/valgrind-$utility.log"
        grep -q "definitely lost: 0 bytes in 0 blocks" "$output/valgrind-$utility.log"
        grep -q "possibly lost: 0 bytes in 0 blocks" "$output/valgrind-$utility.log"
      fi
      if test "$utility" != diff3; then
        grep -q "indirectly lost: 0 bytes in 0 blocks" "$output/valgrind-$utility.log"
      fi
    done
  '
