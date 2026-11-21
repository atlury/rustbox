#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
"$root/scripts/build_attr_hybrid.sh"

RUSTBOX_TOOL_IMAGE=rustbox-attr:2026-11-21 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    output=/work/work/analysis/attr-2.6.0/hybrid
    hybrids=/work/build/attr-2.6.0-hybrid
    canonical=/rustbox-attr/normalized-gcc
    test_build=/rustbox-attr/hybrid-test
    rm -rf "$output" "$test_build"
    mkdir -p "$output"

    python3 /work/tests/attr-oracle-differential.py \
      --gcc-directory /work/work/analysis/attr-2.6.0/oracle --gcc-suffix gcc \
      --clang-directory "$hybrids" --clang-suffix hybrid \
      --output "$output/differential.json"

    cp -a "$canonical" "$test_build"
    for utility in attr getfattr setfattr; do
      cp "$hybrids/$utility-hybrid" "$test_build/$utility"
    done
    chown -R nobody:nogroup "$test_build"
    cd "$test_build"
    if runuser --user=nobody -- make -j"$(nproc)" check \
        >"$output/upstream-tests.log" 2>&1; then
      cat "$output/upstream-tests.log"
    else
      status=$?
      cat "$output/upstream-tests.log"
      exit "$status"
    fi

    cd /rustbox-attr
    for implementation in canonical hybrid; do
      : > valgrind-target
      case $implementation in
        canonical) directory=$canonical; suffix= ;;
        hybrid) directory=$hybrids; suffix=-hybrid ;;
      esac
      valgrind --leak-check=full --show-leak-kinds=all \
        --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
        --log-file="$output/valgrind-setfattr-$implementation.log" \
        "$directory/setfattr$suffix" -n user.rustbox -v canonical \
        valgrind-target
      valgrind --leak-check=full --show-leak-kinds=all \
        --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
        --log-file="$output/valgrind-getfattr-$implementation.log" \
        "$directory/getfattr$suffix" -n user.rustbox \
        valgrind-target \
        >"$output/valgrind-getfattr-$implementation.out"
      for utility in setfattr getfattr; do
        grep -q "ERROR SUMMARY: 0 errors" \
          "$output/valgrind-$utility-$implementation.log"
        sed -n "/HEAP SUMMARY/,+2p" \
          "$output/valgrind-$utility-$implementation.log" \
          | sed "s/^==[0-9]*== *//" \
          >"$output/valgrind-$utility-$implementation-heap"
      done
    done
    cmp "$output/valgrind-getfattr-canonical.out" \
      "$output/valgrind-getfattr-hybrid.out"
    for utility in setfattr getfattr; do
      cmp "$output/valgrind-$utility-canonical-heap" \
        "$output/valgrind-$utility-hybrid-heap"
    done
  '
