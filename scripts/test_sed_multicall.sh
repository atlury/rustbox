#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
exec "$root/scripts/run_multicall_tool.sh" sh -eu -c '
    output=/work/work/analysis/sed-4.10/multicall
    rustbox=${RUSTBOX_TEST_ELF:-/rustbox-coreutils/canonical-clang-no-security-compdb/src/rustbox}
    build=/rustbox-sed/normalized-gcc
    canonical=$build/sed/sed
    installed=$build/sed/sed
    saved=$build/sed/sed.rustbox-canonical
    rm -rf "$output"
    mkdir -p "$output"

    python3 /work/tests/sed-oracle-differential.py \
      --gcc "$canonical" --clang "$rustbox" \
      --output "$output/differential.json"

    test ! -e "$saved"
    mv "$installed" "$saved"
    ln -s "$rustbox" "$installed"
    restore()
    {
      rm -f "$installed"
      mv "$saved" "$installed"
    }
    trap restore EXIT HUP INT TERM
    find "$build/testsuite" "$build/gnulib-tests" -type f \
      \( -name "*.log" -o -name "*.trs" \) -delete
    cd "$build"
    runuser --user=nobody -- make -j"$(nproc)" check \
      > "$output/upstream-tests.log" 2>&1
    restore
    trap - EXIT HUP INT TERM

    printf "alpha old\nbeta old\n" > "$output/valgrind-input"
    valgrind --leak-check=full --show-leak-kinds=all \
      --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
      --log-file="$output/valgrind.log" \
      "$rustbox" sed -n -e p "$output/valgrind-input" \
      > "$output/valgrind.out"
    grep -q "ERROR SUMMARY: 0 errors" "$output/valgrind.log"
    grep -q "definitely lost: 0 bytes in 0 blocks" "$output/valgrind.log"
    grep -q "indirectly lost: 0 bytes in 0 blocks" "$output/valgrind.log"
    grep -q "possibly lost: 0 bytes in 0 blocks" "$output/valgrind.log"
  '
