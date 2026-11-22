#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
"$root/scripts/build_gawk_hybrid.sh"

RUSTBOX_TOOL_IMAGE=rustbox-gawk:2026-11-22 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    output=/work/work/analysis/gawk-5.4.0/hybrid
    hybrid=/work/build/gawk-5.4.0-hybrid
    canonical=/rustbox-gawk/normalized-gcc
    rm -rf "$output"
    mkdir -p "$output"

    python3 /work/tests/gawk-oracle-differential.py \
      --gcc-build "$canonical" --clang-build "$hybrid" \
      --output "$output/differential.json"

    for implementation in hybrid canonical; do
      case $implementation in
        hybrid) binary=$hybrid/gawk ;;
        canonical) binary=$canonical/gawk ;;
      esac
      valgrind --leak-check=full --show-leak-kinds=all \
        --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
        --log-file="$output/valgrind-$implementation.log" \
        "$binary" --version >"$output/valgrind-$implementation.out" 2>&1
      grep -q "ERROR SUMMARY: 0 errors" "$output/valgrind-$implementation.log"
      grep -q "definitely lost: 0 bytes" "$output/valgrind-$implementation.log"
      grep -q "indirectly lost: 0 bytes" "$output/valgrind-$implementation.log"
      grep -q "possibly lost: 0 bytes" "$output/valgrind-$implementation.log"
    done
    cmp "$output/valgrind-canonical.out" "$output/valgrind-hybrid.out"
  '
