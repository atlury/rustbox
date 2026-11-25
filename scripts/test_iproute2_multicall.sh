#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
exec "$root/scripts/run_multicall_tool.sh" sh -eu -c '
    rustbox=${RUSTBOX_TEST_ELF:-/rustbox-coreutils/canonical-clang-no-security-compdb/src/rustbox}
    canonical=/rustbox-iproute2/programs-gcc
    routel=/work/work/upstream/iproute2-7.3.0/ip/routel
    output=/work/work/analysis/iproute2-7.3.0/multicall
    programs="arpd bridge dcb devlink dpll genl ifstat ip lnstat netshaper nstat rdma rtacct rtmon ss tc tipc vdpa ctstat rtstat routel"

    test -x "$rustbox"
    test -x "$canonical/ip"
    test -f "$routel"
    mkdir -p "$output"
    python3 -B /work/tests/iproute2-multicall-differential.py \
      --canonical-root "$canonical" \
      --canonical-routel "$routel" \
      --rustbox "$rustbox" \
      --output "$output/differential.json"

    for name in $programs; do
      valgrind --leak-check=full --show-leak-kinds=all \
        --errors-for-leak-kinds=definite,indirect,possible \
        --log-file="$output/valgrind-$name.log" \
        "$rustbox" "$name" -h >"$output/valgrind-$name.out" 2>&1 || true
      grep -q "ERROR SUMMARY: 0 errors" "$output/valgrind-$name.log"
      if ! grep -q "All heap blocks were freed -- no leaks are possible" \
          "$output/valgrind-$name.log"; then
        grep -q "definitely lost: 0 bytes" "$output/valgrind-$name.log"
        grep -q "indirectly lost: 0 bytes" "$output/valgrind-$name.log"
        grep -q "possibly lost: 0 bytes" "$output/valgrind-$name.log"
      fi
    done
    test "$(find "$output" -name "valgrind-*.log" -type f | wc -l)" -eq 21
    chmod -R a+rwX "$output"
  '
