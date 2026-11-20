#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)

RUSTBOX_TOOL_IMAGE=rustbox-file:2026-11-20 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    output=/work/work/analysis/m4-1.4.21/multicall
    rustbox=/rustbox-coreutils/canonical-clang-no-security-compdb/src/rustbox
    canonical=/rustbox-m4/normalized-clang/src/m4
    bindir="$output/bin"
    mkdir -p "$bindir"
    ln -sf "$rustbox" "$bindir/m4"

    cd /rustbox-m4/normalized-clang/checks
    PATH="$bindir:$PATH"
    export PATH
    /rustbox-m4/normalized-source/checks/check-them \
      -I /rustbox-m4/normalized-source/examples \
      /rustbox-m4/normalized-source/checks/*[0-9][0-9][0-9].* \
      /rustbox-m4/normalized-source/checks/stackovf.test \
      > "$output/language-check.log" 2>&1

    python3 /work/tests/m4-differential.py \
      --canonical "$canonical" --hybrid "$rustbox" \
      --output "$output/differential.json"

    printf "define(\140twice\047, \140\$1\$1\047)dnl\ntwice(\140rustbox\047)\n" \
      > "$output/valgrind.m4"
    valgrind --leak-check=full --show-leak-kinds=all \
      --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
      --log-file="$output/valgrind.log" \
      "$bindir/m4" "$output/valgrind.m4" > "$output/valgrind.out"
    test "$(cat "$output/valgrind.out")" = rustboxrustbox
    grep -q "ERROR SUMMARY: 0 errors" "$output/valgrind.log"
    grep -q "definitely lost: 0 bytes in 0 blocks" "$output/valgrind.log"
    grep -q "indirectly lost: 0 bytes in 0 blocks" "$output/valgrind.log"
    grep -q "possibly lost: 0 bytes in 0 blocks" "$output/valgrind.log"
  '
