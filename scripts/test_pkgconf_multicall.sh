#!/bin/sh
# SPDX-License-Identifier: ISC
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
exec "$root/scripts/run_multicall_tool.sh" sh -eu -c '
    output=/work/work/analysis/pkgconf-3.0.11/multicall
    rustbox=/rustbox-coreutils/canonical-clang-no-security-compdb/src/rustbox
    source=/rustbox-pkgconf/normalized-source
    runner=/rustbox-pkgconf/normalized-gcc-static/test-runner
    bindir=$output/bin
    canonical=$output/canonical-bin
    rm -rf "$output"
    mkdir -p "$bindir" "$canonical"
    for name in pkgconf pkg-config bomtool pccritic spdxtool; do
      ln -s "$rustbox" "$bindir/$name"
    done
    for name in pkgconf bomtool pccritic spdxtool; do
      ln -s /rustbox-pkgconf/normalized-clang-static/$name "$canonical/$name"
    done
    ln -s /rustbox-pkgconf/normalized-clang-static/pkgconf "$canonical/pkg-config"

    : > "$output/fixture-tests.log"
    count=0
    for suite in "$source"/t/*; do
      test -d "$suite" || continue
      echo "== $(basename "$suite") ==" >> "$output/fixture-tests.log"
      "$runner" --test-fixtures "$source/tests" --tool-dir "$bindir" "$suite" \
        >> "$output/fixture-tests.log" 2>&1
      count=$((count + 1))
    done
    test "$count" -eq 14

    python3 /work/tests/pkgconf-differential.py \
      --canonical-dir "$canonical" --hybrid-dir "$bindir" \
      --output "$output/differential.json"

    valgrind --leak-check=full --show-leak-kinds=all \
      --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
      --log-file="$output/valgrind.log" "$rustbox" pkgconf --help \
      >/dev/null 2>/dev/null
    grep -q "ERROR SUMMARY: 0 errors" "$output/valgrind.log"
    grep -q "All heap blocks were freed -- no leaks are possible" "$output/valgrind.log"
  '
