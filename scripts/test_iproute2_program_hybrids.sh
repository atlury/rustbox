#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-iproute2:2026-11-24 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    output=/work/work/analysis/iproute2-7.3.0/program-hybrids
    hybrids=/rustbox-iproute2/program-hybrids
    programs="arpd bridge dcb devlink dpll genl ifstat ip lnstat netshaper nstat rdma rtacct rtmon ss tc tipc vdpa"

    python3 -B /work/tests/iproute2-hybrid-differential.py \
      --canonical-root /rustbox-iproute2/programs-gcc \
      --hybrid-root "$hybrids" \
      --output "$output/differential.json"

    for name in $programs; do
      valgrind --leak-check=full --show-leak-kinds=all \
        --errors-for-leak-kinds=definite,indirect,possible \
        --log-file="$output/valgrind-$name.log" \
        "$hybrids/$name" -h >"$output/valgrind-$name.out" 2>&1 || true
      grep -q "ERROR SUMMARY: 0 errors" "$output/valgrind-$name.log"
      if ! grep -q "All heap blocks were freed -- no leaks are possible" \
          "$output/valgrind-$name.log"; then
        grep -q "definitely lost: 0 bytes" "$output/valgrind-$name.log"
        grep -q "indirectly lost: 0 bytes" "$output/valgrind-$name.log"
        grep -q "possibly lost: 0 bytes" "$output/valgrind-$name.log"
      fi
    done
    chmod -R a+rwX "$output"
  '
