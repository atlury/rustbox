#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-iproute2:2026-11-24 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    output=/work/work/analysis/iproute2-7.3.0/oracle
    programs="arpd bridge ctstat dcb devlink dpll genl ifstat ip lnstat netshaper nstat rdma rtacct rtmon rtstat ss tc tipc vdpa"
    for name in $programs; do
      valgrind --leak-check=full --show-leak-kinds=all \
        --errors-for-leak-kinds=definite,indirect,possible \
        --log-file="$output/valgrind-$name.log" \
        "/rustbox-iproute2/programs-gcc/$name" -h \
        >"$output/valgrind-$name.out" 2>&1 || true
    done
    printf "canonical Python frontend; native Valgrind not applicable\n" \
      >"$output/valgrind-routel.log"
    chmod -R a+rwX "$output"
  '
