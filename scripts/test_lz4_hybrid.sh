#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-lz4:2026-11-21 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    hybrid=/work/build/lz4-1.11.1-hybrid
    canonical=/work/work/analysis/lz4-1.11.1/normalized/gcc
    analysis=/work/work/analysis/lz4-1.11.1/hybrid
    source=/rustbox-lz4/hybrid-test-source
    rm -rf "$analysis" "$source"
    mkdir -p "$analysis"

    python3 /work/tests/lz4-oracle-differential.py \
      --gcc-directory "$canonical" --clang-directory "$hybrid" \
      --output "$analysis/differential.json"

    cp -a /rustbox-lz4/normalized-source "$source"
    make -j"$(nproc)" -C "$source/tests" datagen checkFrame
    cp "$hybrid/lz4" "$source/programs/lz4"
    for alias in lz4c lz4cat unlz4; do
      ln -sf lz4 "$source/programs/$alias"
    done
    if make -j"$(nproc)" -C "$source/tests" -o lz4 \
        LZ4="$source/programs/lz4" test-lz4-essentials \
        >"$analysis/upstream-tests.log" 2>&1
    then
      cat "$analysis/upstream-tests.log"
    else
      status=$?
      cat "$analysis/upstream-tests.log"
      exit "$status"
    fi

    cd /rustbox-lz4
    printf "the quick brown fox\n%.0s" $(seq 1 1024) > hybrid-valgrind-input
    "$canonical/lz4" -f hybrid-valgrind-input hybrid-valgrind-input.canonical.lz4
    for implementation in canonical hybrid; do
      if test "$implementation" = canonical; then binary=$canonical/lz4; else binary=$hybrid/lz4; fi
      valgrind --leak-check=full --show-leak-kinds=all \
        --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
        --log-file="$analysis/valgrind-compress-$implementation.log" \
        "$binary" -f hybrid-valgrind-input "hybrid-valgrind-input.$implementation.lz4"
      valgrind --leak-check=full --show-leak-kinds=all \
        --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
        --log-file="$analysis/valgrind-decompress-$implementation.log" \
        "$binary" -d -f hybrid-valgrind-input.canonical.lz4 \
          "hybrid-valgrind-output.$implementation"
      grep -q "ERROR SUMMARY: 0 errors" "$analysis/valgrind-compress-$implementation.log"
      grep -q "ERROR SUMMARY: 0 errors" "$analysis/valgrind-decompress-$implementation.log"
      grep -q "All heap blocks were freed -- no leaks are possible" \
        "$analysis/valgrind-compress-$implementation.log"
      grep -q "All heap blocks were freed -- no leaks are possible" \
        "$analysis/valgrind-decompress-$implementation.log"
    done
    cmp hybrid-valgrind-input.canonical.lz4 hybrid-valgrind-input.hybrid.lz4
    cmp hybrid-valgrind-output.canonical hybrid-valgrind-output.hybrid
  '
