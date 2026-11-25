#!/bin/sh
# SPDX-License-Identifier: BSD-2-Clause
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
exec "$root/scripts/run_multicall_tool.sh" sh -eu -c '
    output=/work/work/analysis/file-5.48/multicall
    rustbox=/rustbox-coreutils/canonical-clang-no-security-compdb/src/rustbox
    source=/rustbox-file/normalized-source
    magic=/rustbox-file/canonical-gcc/magic/magic
    rm -rf "$output"
    mkdir -p "$output/bin"
    ln -s "$rustbox" "$output/bin/file"

    python3 /work/tests/file-oracle-differential.py \
      --gcc /rustbox-file/canonical-gcc/src/file \
      --clang "$output/bin/file" --magic "$magic" \
      --upstream-tests "$source/tests" \
      --output "$output/differential.json"

    printf "rustbox integrated file\n" > "$output/valgrind-input.txt"
    valgrind --leak-check=full --show-leak-kinds=all \
      --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
      --log-file="$output/valgrind.log" \
      "$rustbox" file --no-sandbox -m "$magic" "$output/valgrind-input.txt" \
      > "$output/valgrind.out"
    grep -q "ERROR SUMMARY: 0 errors" "$output/valgrind.log"
    grep -q "All heap blocks were freed -- no leaks are possible" \
      "$output/valgrind.log"
  '
