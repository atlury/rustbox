#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-iproute2:2026-11-24 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    output=/work/work/analysis/iproute2-7.3.0/routel-frontend
    mkdir -p "$output"
    for compiler in gcc clang-18; do
      "$compiler" -std=c11 -O2 -g -Wall -Wextra -Werror \
        /work/bridges/iproute2_routel.c \
        /work/tests/iproute2-routel-mock.c \
        -o "$output/routel-mock-$compiler"
      "$compiler" -std=c11 -O2 -g -Wall -Wextra -Werror \
        -DRUSTBOX_MULTICALL -c /work/bridges/iproute2_routel.c \
        -o "$output/routel-$compiler.o"
      nm -g --defined-only "$output/routel-$compiler.o" \
        >"$output/routel-$compiler.symbols"
      test "$(awk '\''$NF == "rustbox_iproute2_routel_main" { n++ } END { print n+0 }'\'' \
        "$output/routel-$compiler.symbols")" -eq 1
      test "$(wc -l <"$output/routel-$compiler.symbols")" -eq 1
    done
    python3 -B /work/tests/iproute2-routel-frontend.py \
      --canonical /work/work/upstream/iproute2-7.3.0/ip/routel \
      --native "$output/routel-mock-gcc" \
      --native "$output/routel-mock-clang-18" \
      --output "$output/synthetic-differential.json"
    for compiler in gcc clang-18; do
      RUSTBOX_ROUTEL_JSON="[]" valgrind --leak-check=full \
        --show-leak-kinds=all \
        --errors-for-leak-kinds=definite,indirect,possible \
        --error-exitcode=99 --log-file="$output/valgrind-$compiler.log" \
        "$output/routel-mock-$compiler" >"$output/valgrind-$compiler.out"
      grep -q "ERROR SUMMARY: 0 errors" "$output/valgrind-$compiler.log"
      grep -Eq "All heap blocks were freed|definitely lost: 0 bytes" \
        "$output/valgrind-$compiler.log"
      grep -Eq "All heap blocks were freed|indirectly lost: 0 bytes" \
        "$output/valgrind-$compiler.log"
      grep -Eq "All heap blocks were freed|possibly lost: 0 bytes" \
        "$output/valgrind-$compiler.log"
    done
    chmod -R a+rwX "$output"
  '
