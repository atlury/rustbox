#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-kmod:2026-11-24 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    output=/work/work/analysis/kmod-34.3/oracle
    gcc=/rustbox-kmod/oracle-gcc
    clang=/rustbox-kmod/oracle-clang
    python3 /work/tests/kmod-oracle-differential.py \
      --gcc-root "$gcc" --clang-root "$clang" \
      --output "$output/differential.json"
    for name in kmod depmod insmod lsmod modinfo modprobe rmmod; do
      valgrind --leak-check=full --show-leak-kinds=all \
        --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
        --log-file="$output/valgrind-$name.log" \
        "$gcc/$name" --version >"$output/valgrind-$name.out"
      grep -q "ERROR SUMMARY: 0 errors" "$output/valgrind-$name.log"
      if ! grep -q "All heap blocks were freed -- no leaks are possible" \
          "$output/valgrind-$name.log"; then
        grep -q "definitely lost: 0 bytes in 0 blocks" "$output/valgrind-$name.log"
        grep -q "indirectly lost: 0 bytes in 0 blocks" "$output/valgrind-$name.log"
        grep -q "possibly lost: 0 bytes in 0 blocks" "$output/valgrind-$name.log"
      fi
    done
    chmod -R a+rwX "$output"
  '
