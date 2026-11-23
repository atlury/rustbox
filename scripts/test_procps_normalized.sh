#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-procps:2026-11-24 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    evidence=/work/work/analysis/procps-ng-4.0.7/normalized
    oracle_gcc=/rustbox-procps/programs-gcc
    oracle_clang=/rustbox-procps/programs-clang-18
    normalized_gcc=/rustbox-procps/normalized-programs-gcc
    normalized_clang=/rustbox-procps/normalized-programs-clang-18
    oracle_gcc_library=/rustbox-procps/oracle-gcc/library/.libs
    oracle_clang_library=/rustbox-procps/oracle-clang-18/library/.libs
    normalized_gcc_library=/rustbox-procps/normalized-gcc/library/.libs
    normalized_clang_library=/rustbox-procps/normalized-clang-18/library/.libs
    programs="free hugetop kill pgrep pidof pidwait pkill pmap ps pwdx skill slabtop snice sysctl tload top uptime vmstat w watch"

    python3 /work/tests/procps-oracle-differential.py \
      --gcc-root "$oracle_gcc" --gcc-library "$oracle_gcc_library" \
      --clang-root "$normalized_gcc" --clang-library "$normalized_gcc_library" \
      --output "$evidence/gcc-differential.json"
    python3 /work/tests/procps-oracle-differential.py \
      --gcc-root "$oracle_clang" --gcc-library "$oracle_clang_library" \
      --clang-root "$normalized_clang" --clang-library "$normalized_clang_library" \
      --output "$evidence/clang-differential.json"

    for name in $programs; do
      set +e
      LD_LIBRARY_PATH="$normalized_clang_library" \
        valgrind --leak-check=full --show-leak-kinds=all \
          --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
          --log-file="$evidence/valgrind-$name.log" \
          "$normalized_clang/$name" --version >"$evidence/valgrind-$name.out" 2>&1
      status=$?
      set -e
      if test "$name" = sysctl; then
        test "$status" -eq 99
        grep -q "ERROR SUMMARY: 1 errors from 1 contexts" "$evidence/valgrind-$name.log"
        grep -q "definitely lost: 16 bytes in 1 blocks" "$evidence/valgrind-$name.log"
      else
        test "$status" -eq 0
        grep -q "ERROR SUMMARY: 0 errors" "$evidence/valgrind-$name.log"
      fi
    done
    chmod -R a+rwX "$evidence"
  '
