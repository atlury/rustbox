#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-kmod:2026-11-24 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    canonical=/rustbox-kmod/oracle-gcc
    rustbox=/rustbox-coreutils/canonical-clang-no-security-compdb/src/rustbox
    dispatch=/rustbox-kmod/multicall-dispatch
    evidence=/work/work/analysis/kmod-34.3/multicall
    rm -rf "$dispatch" "$evidence"
    mkdir -p "$dispatch" "$evidence"
    for name in kmod depmod insmod lsmod modinfo modprobe rmmod; do
      ln -s "$rustbox" "$dispatch/$name"
    done

    python3 /work/tests/kmod-oracle-differential.py \
      --gcc-root "$canonical" --clang-root "$dispatch" \
      --output "$evidence/differential.json"
    for name in kmod depmod insmod lsmod modinfo modprobe rmmod; do
      valgrind --leak-check=full --show-leak-kinds=all \
        --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
        --log-file="$evidence/valgrind-$name.log" \
        "$dispatch/$name" --version >"$evidence/valgrind-$name.out"
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
