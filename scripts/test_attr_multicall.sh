#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
exec "$root/scripts/run_multicall_tool.sh" sh -eu -c '
    output=/work/work/analysis/attr-2.6.0/multicall
    rustbox=/rustbox-coreutils/canonical-clang-no-security-compdb/src/rustbox
    canonical=/rustbox-attr/normalized-gcc
    test_build=/rustbox-attr/multicall-test
    dispatch=/rustbox-attr/multicall-dispatch
    rm -rf "$output" "$test_build" "$dispatch"
    mkdir -p "$output" "$dispatch"

    for utility in attr getfattr setfattr; do
      ln -s "$rustbox" "$dispatch/$utility-rustbox"
    done
    python3 /work/tests/attr-oracle-differential.py \
      --gcc-directory /work/work/analysis/attr-2.6.0/oracle --gcc-suffix gcc \
      --clang-directory "$dispatch" --clang-suffix rustbox \
      --output "$output/differential.json"

    cp -a "$canonical" "$test_build"
    for utility in attr getfattr setfattr; do
      cp "$rustbox" "$test_build/$utility"
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
    : > valgrind-target
    valgrind --leak-check=full --show-leak-kinds=all \
      --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
      --log-file="$output/valgrind-setfattr.log" \
      "$rustbox" setfattr -n user.rustbox -v canonical valgrind-target
    valgrind --leak-check=full --show-leak-kinds=all \
      --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
      --log-file="$output/valgrind-getfattr.log" \
      "$rustbox" getfattr -n user.rustbox valgrind-target \
      >"$output/valgrind-getfattr.out"
    for utility in setfattr getfattr; do
      grep -q "ERROR SUMMARY: 0 errors" "$output/valgrind-$utility.log"
      sed -n "/HEAP SUMMARY/,+2p" "$output/valgrind-$utility.log" \
        | sed "s/^==[0-9]*== *//" >"$output/valgrind-$utility-heap"
      cmp "$output/valgrind-$utility-heap" \
        "/work/work/analysis/attr-2.6.0/hybrid/valgrind-$utility-hybrid-heap"
    done
    cmp "$output/valgrind-getfattr.out" \
      "/work/work/analysis/attr-2.6.0/hybrid/valgrind-getfattr-hybrid.out"
  '
