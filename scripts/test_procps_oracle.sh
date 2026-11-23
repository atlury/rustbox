#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-procps:2026-11-24 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    evidence=/work/work/analysis/procps-ng-4.0.7/oracle
    gcc=/rustbox-procps/programs-gcc
    clang=/rustbox-procps/programs-clang-18
    gcc_library=/rustbox-procps/oracle-gcc/library/.libs
    clang_library=/rustbox-procps/oracle-clang-18/library/.libs
    programs="free hugetop kill pgrep pidof pidwait pkill pmap ps pwdx skill slabtop snice sysctl tload top uptime vmstat w watch"

    python3 /work/tests/procps-oracle-differential.py \
      --gcc-root "$gcc" --gcc-library "$gcc_library" \
      --clang-root "$clang" --clang-library "$clang_library" \
      --output "$evidence/differential.json"
    for name in $programs; do
      set +e
      LD_LIBRARY_PATH="$gcc_library" \
        valgrind --leak-check=full --show-leak-kinds=all \
          --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
          --log-file="$evidence/valgrind-$name.log" \
          "$gcc/$name" --version >"$evidence/valgrind-$name.out" 2>&1
      status=$?
      set -e
      if test "$name" = sysctl; then
        test "$status" -eq 99
        grep -q "ERROR SUMMARY: 1 errors from 1 contexts" "$evidence/valgrind-$name.log"
        grep -q "definitely lost: 16 bytes in 1 blocks" "$evidence/valgrind-$name.log"
        grep -q "indirectly lost: 0 bytes in 0 blocks" "$evidence/valgrind-$name.log"
        grep -q "possibly lost: 0 bytes in 0 blocks" "$evidence/valgrind-$name.log"
      else
        test "$status" -eq 0
        grep -q "ERROR SUMMARY: 0 errors" "$evidence/valgrind-$name.log"
        if ! grep -q "All heap blocks were freed -- no leaks are possible" \
            "$evidence/valgrind-$name.log"; then
          grep -q "definitely lost: 0 bytes in 0 blocks" "$evidence/valgrind-$name.log"
          grep -q "indirectly lost: 0 bytes in 0 blocks" "$evidence/valgrind-$name.log"
          grep -q "possibly lost: 0 bytes in 0 blocks" "$evidence/valgrind-$name.log"
        fi
      fi
    done
    chmod -R a+rwX "$evidence"
  '
