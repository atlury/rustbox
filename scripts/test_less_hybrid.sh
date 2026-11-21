#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-less:2026-11-22 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    hybrid=/work/build/less-710-hybrid
    canonical=/work/work/analysis/less-710/normalized/gcc
    analysis=/work/work/analysis/less-710/hybrid
    rm -rf "$analysis"
    mkdir -p "$analysis"

    python3 /work/tests/less-oracle-differential.py \
      --gcc-directory "$canonical" --clang-directory "$hybrid" \
      --output "$analysis/differential.json"

    printf "alpha beta gamma\n%.0s" $(seq 1 1024) >"$analysis/input"
    for implementation in canonical hybrid; do
      if test "$implementation" = canonical; then directory=$canonical; else directory=$hybrid; fi
      LESSHISTFILE=- TERM=xterm valgrind --leak-check=full --show-leak-kinds=all \
        --errors-for-leak-kinds=definite,indirect --error-exitcode=99 \
        --log-file="$analysis/valgrind-less-$implementation.log" \
        "$directory/less" "$analysis/input" >"$analysis/less-$implementation.out"
      valgrind --leak-check=full --show-leak-kinds=all \
        --errors-for-leak-kinds=definite,indirect --error-exitcode=99 \
        --log-file="$analysis/valgrind-lessecho-$implementation.log" \
        "$directory/lessecho" -a "alpha beta" >"$analysis/lessecho-$implementation.out"
      for applet in less lessecho; do
        grep -q "ERROR SUMMARY: 0 errors" "$analysis/valgrind-$applet-$implementation.log"
        if grep -q "LEAK SUMMARY" "$analysis/valgrind-$applet-$implementation.log"; then
          grep -q "definitely lost: 0 bytes" "$analysis/valgrind-$applet-$implementation.log"
          grep -q "indirectly lost: 0 bytes" "$analysis/valgrind-$applet-$implementation.log"
        else
          grep -q "All heap blocks were freed -- no leaks are possible" \
            "$analysis/valgrind-$applet-$implementation.log"
        fi
      done
    done
    cmp "$analysis/less-canonical.out" "$analysis/less-hybrid.out"
    cmp "$analysis/lessecho-canonical.out" "$analysis/lessecho-hybrid.out"
  '
