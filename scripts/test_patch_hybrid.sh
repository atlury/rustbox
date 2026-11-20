#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
"$root/scripts/build_patch_hybrid.sh"

RUSTBOX_TOOL_IMAGE=rustbox-patch:2026-11-20 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    output=/work/work/analysis/patch-2.8/hybrid
    hybrid=/work/build/patch-2.8-hybrid/patch
    canonical=/rustbox-patch/normalized-gcc/src/patch
    build=/rustbox-patch/normalized-gcc
    installed=$build/src/patch
    saved=$build/src/patch.rustbox-canonical
    rm -rf "$output"
    mkdir -p "$output"

    python3 /work/tests/patch-oracle-differential.py \
      --gcc "$canonical" --clang "$hybrid" \
      --output "$output/differential.json"

    test ! -e "$saved"
    mv "$installed" "$saved"
    ln -s /work/build/patch-2.8-hybrid/patch-hybrid "$installed"
    restore()
    {
      rm -f "$installed"
      mv "$saved" "$installed"
    }
    trap restore EXIT HUP INT TERM
    find "$build/tests" -maxdepth 1 -type f \
      \( -name "*.log" -o -name "*.trs" \) -delete
    cd "$build"
    runuser --user=nobody -- make -j"$(nproc)" check \
      > "$output/upstream-tests.log" 2>&1
    restore
    trap - EXIT HUP INT TERM

    mkdir "$output/valgrind-case"
    printf "old line\nsecond line\n" > "$output/valgrind-case/input"
    printf "%s\n" \
      "--- input" "+++ input" "@@ -1,2 +1,2 @@" \
      "-old line" "+new line" " second line" \
      > "$output/valgrind-case/change.diff"
    cd "$output/valgrind-case"
    valgrind --leak-check=full --show-leak-kinds=all \
      --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
      --log-file="$output/valgrind.log" \
      "$hybrid" -i change.diff input > "$output/valgrind.out"
    grep -q "ERROR SUMMARY: 0 errors" "$output/valgrind.log"
    grep -q "definitely lost: 0 bytes in 0 blocks" "$output/valgrind.log"
    grep -q "indirectly lost: 0 bytes in 0 blocks" "$output/valgrind.log"
    grep -q "possibly lost: 0 bytes in 0 blocks" "$output/valgrind.log"
    test "$(sed -n 1p input)" = "new line"
  '
