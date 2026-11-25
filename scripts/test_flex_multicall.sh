#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
exec "$root/scripts/run_multicall_tool.sh" sh -eu -c '
    analysis=/work/work/analysis/flex-2.6.4/multicall
    canonical=/rustbox-flex/normalized-gcc/src/flex
    rustbox=/rustbox-coreutils/canonical-clang-no-security-compdb/src/rustbox
    source=/rustbox-flex/normalized-source
    suite=/rustbox-flex/hybrid-suite
    mkdir -p "$analysis" /work/build/rustbox-flex-dispatch
    ln -sf "$rustbox" /work/build/rustbox-flex-dispatch/flex
    multicall_flex=/work/build/rustbox-flex-dispatch/flex

    python3 /work/tests/flex-oracle-differential.py \
      --gcc "$canonical" --clang "$multicall_flex" --source "$source" \
      --output "$analysis/differential.json"
    python3 /work/tests/flex-hybrid-frontends.py \
      --canonical "$canonical" --hybrid "$rustbox" --source "$source" \
      --output "$analysis/frontends.json"

    make -C "$suite/tests" clean >"$analysis/upstream-clean.log" 2>&1
    make -C "$suite" -j"$(nproc)" check FLEX="$multicall_flex" \
      >"$analysis/upstream-tests.log" 2>&1

    for name in flex flex++ lex; do
      ln -sf "$rustbox" "/work/build/rustbox-flex-dispatch/$name"
      valgrind --leak-check=full --show-leak-kinds=all \
        --log-file="$analysis/valgrind-$name-version.log" \
        "/work/build/rustbox-flex-dispatch/$name" --version \
        >"$analysis/valgrind-$name-version.out" 2>&1
      grep -q "ERROR SUMMARY: 0 errors" "$analysis/valgrind-$name-version.log"
      grep -q "definitely lost: 0 bytes" "$analysis/valgrind-$name-version.log"
      grep -q "indirectly lost: 0 bytes" "$analysis/valgrind-$name-version.log"
      grep -q "possibly lost: 0 bytes" "$analysis/valgrind-$name-version.log"
    done

    status=0
    valgrind --leak-check=full --show-leak-kinds=all \
      --log-file="$analysis/valgrind-flex-invalid.log" \
      "$multicall_flex" --definitely-invalid \
      >"$analysis/valgrind-flex-invalid.out" 2>&1 || status=$?
    test "$status" -ne 0
    grep -q "ERROR SUMMARY: 0 errors" "$analysis/valgrind-flex-invalid.log"
    grep -q "definitely lost: 0 bytes" "$analysis/valgrind-flex-invalid.log"
    grep -q "indirectly lost: 0 bytes" "$analysis/valgrind-flex-invalid.log"
    grep -q "possibly lost: 0 bytes" "$analysis/valgrind-flex-invalid.log"
  '
