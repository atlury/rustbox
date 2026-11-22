#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-flex:2026-11-22 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    analysis=/work/work/analysis/flex-2.6.4
    canonical=/rustbox-flex/normalized-gcc/src/flex
    hybrid=/work/build/flex-2.6.4-hybrid/flex
    source=/rustbox-flex/normalized-source
    suite=/rustbox-flex/hybrid-suite

    python3 /work/tests/flex-oracle-differential.py \
      --gcc "$canonical" --clang "$hybrid" --source "$source" \
      --output "$analysis/translated-differential.json"
    python3 /work/tests/flex-hybrid-frontends.py \
      --canonical "$canonical" --hybrid "$hybrid" --source "$source" \
      --output "$analysis/hybrid-frontends.json"

    if test ! -f "$suite/.rustbox-copy-complete"; then
      mkdir -p "$suite"
      cp -R /rustbox-flex/normalized-gcc/. "$suite/"
      touch "$suite/.rustbox-copy-complete"
    fi
    make -C "$suite/tests" clean >"$analysis/hybrid-suite-clean.log" 2>&1
    make -C "$suite" -j"$(nproc)" check FLEX="$hybrid" \
      >"$analysis/hybrid-suite-check.log" 2>&1

    for label in help version invalid; do
      option=--$label
      test "$label" != invalid || option=--definitely-invalid
      status=0
      valgrind --leak-check=full --show-leak-kinds=all \
        --log-file="$analysis/hybrid-valgrind-$label.log" \
        "$hybrid" "$option" >"$analysis/hybrid-valgrind-$label.out" 2>&1 \
        || status=$?
      test "$label" = invalid || test "$status" -eq 0
      test "$label" != invalid || test "$status" -ne 0
      grep -q "ERROR SUMMARY: 0 errors" "$analysis/hybrid-valgrind-$label.log"
      grep -q "definitely lost: 0 bytes" "$analysis/hybrid-valgrind-$label.log"
      grep -q "indirectly lost: 0 bytes" "$analysis/hybrid-valgrind-$label.log"
      grep -q "possibly lost: 0 bytes" "$analysis/hybrid-valgrind-$label.log"
    done
  '
