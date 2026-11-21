#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
"$root/scripts/build_bc_hybrid.sh"

RUSTBOX_TOOL_IMAGE=rustbox-bc:2026-11-21 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    output=/work/work/analysis/bc-1.08.2/hybrid
    hybrids=/work/build/bc-1.08.2-hybrid
    canonical=/rustbox-bc/normalized-gcc
    source=/rustbox-bc/normalized-source
    rm -rf "$output"
    mkdir -p "$output"

    python3 /work/tests/bc-oracle-differential.py \
      --gcc-bc "$canonical/bc/bc" --clang-bc "$hybrids/bc-hybrid" \
      --gcc-dc "$canonical/dc/dc" --clang-dc "$hybrids/dc-hybrid" \
      --output "$output/differential.json"

    : >"$output/upstream-tests.log"
    for test_file in "$source"/Test/*.b "$source"/Test/*.bc; do
      test_name=$(basename "$test_file")
      case $test_name in checklib.b) test_timeout=1800 ;; *) test_timeout=600 ;; esac
      timeout "$test_timeout" "$hybrids/bc-hybrid" -q -l "$test_file" </dev/null \
        >"$output/$test_name.out" 2>"$output/$test_name.err"
      cmp "$output/$test_name.out" "/work/work/analysis/bc-1.08.2/normalized/gcc-$test_name.out"
      cmp "$output/$test_name.err" "/work/work/analysis/bc-1.08.2/normalized/gcc-$test_name.err"
      printf "%s pass\n" "$test_name" >>"$output/upstream-tests.log"
    done

    printf "scale=30\n1/7\n" >"$output/valgrind-bc.input"
    printf "20 k 1 7 / p\n" >"$output/valgrind-dc.input"
    for utility in bc dc; do
      case $utility in bc) arguments=-q ;; dc) arguments= ;; esac
      for implementation in hybrid canonical; do
        case $implementation in
          hybrid) binary=$hybrids/$utility-hybrid ;;
          canonical) binary=$canonical/$utility/$utility ;;
        esac
        valgrind --leak-check=full --show-leak-kinds=all \
          --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
          --log-file="$output/valgrind-$utility-$implementation.log" \
          "$binary" $arguments \
          <"$output/valgrind-$utility.input" \
          >"$output/valgrind-$utility-$implementation.out"
        grep -q "ERROR SUMMARY: 0 errors" \
          "$output/valgrind-$utility-$implementation.log"
        sed -n "/HEAP SUMMARY/,+2p" \
          "$output/valgrind-$utility-$implementation.log" \
          | sed "s/^==[0-9]*== *//" \
          >"$output/valgrind-$utility-$implementation-heap"
      done
      cmp "$output/valgrind-$utility-canonical.out" \
        "$output/valgrind-$utility-hybrid.out"
      cmp "$output/valgrind-$utility-canonical-heap" \
        "$output/valgrind-$utility-hybrid-heap"
    done
  '
