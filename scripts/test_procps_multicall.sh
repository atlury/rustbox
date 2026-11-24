#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-procps:2026-11-24 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    oracle=/rustbox-procps/programs-gcc
    oracle_library=/rustbox-procps/oracle-gcc/library/.libs
    rustbox=/rustbox-coreutils/canonical-clang-no-security-compdb/src/rustbox
    evidence=/work/work/analysis/procps-ng-4.0.7/multicall
    rm -rf "$evidence"
    mkdir -p "$evidence"

    python3 /work/tests/procps-oracle-differential.py \
      --gcc-root "$oracle" --gcc-library "$oracle_library" \
      --clang-root /nonexistent --clang-library /nonexistent \
      --clang-multicall "$rustbox" \
      --output "$evidence/differential.json"

    for name in free hugetop procps-kill pgrep pidof pidwait pkill pmap ps pwdx \
        skill slabtop snice sysctl tload top procps-uptime vmstat w watch; do
      valgrind --leak-check=full --show-leak-kinds=all \
        --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
        --log-file="$evidence/valgrind-$name.log" \
        "$rustbox" "$name" --version >"$evidence/valgrind-$name.out" || {
          test "$name" = sysctl
          grep -q "16 bytes in 1 blocks" "$evidence/valgrind-$name.log"
          grep -q "ERROR SUMMARY: 1 errors" "$evidence/valgrind-$name.log"
          continue
        }
      grep -q "ERROR SUMMARY: 0 errors" "$evidence/valgrind-$name.log"
      if ! grep -q "All heap blocks were freed -- no leaks are possible" \
          "$evidence/valgrind-$name.log"; then
        grep -q "definitely lost: 0 bytes in 0 blocks" "$evidence/valgrind-$name.log"
        grep -q "indirectly lost: 0 bytes in 0 blocks" "$evidence/valgrind-$name.log"
        grep -q "possibly lost: 0 bytes in 0 blocks" "$evidence/valgrind-$name.log"
      fi
    done
    chmod -R a+rwX "$evidence"
  '
