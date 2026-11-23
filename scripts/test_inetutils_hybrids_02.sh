#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-inetutils:2026-11-23 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    canonical=/rustbox-inetutils/normalized-gcc
    hybrid=/rustbox-inetutils/program-hybrid
    evidence=/work/work/analysis/inetutils-2.8/program-hybrids
    python3 /work/tests/inetutils-clients-02-differential.py \
      --canonical-root "$canonical" --hybrid-root "$hybrid" \
      --output "$evidence/differential-02.json"
    for name in rexec tftp traceroute ifconfig ping ping6; do
      valgrind --leak-check=full --show-leak-kinds=all \
        --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
        --log-file="$evidence/valgrind-$name.log" \
        "$hybrid/$name" --version >"$evidence/valgrind-$name.out"
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
