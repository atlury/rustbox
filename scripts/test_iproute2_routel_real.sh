#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-iproute2:2026-11-24 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    base=/work/work/analysis/iproute2-7.3.0/program-translations
    archive=$base/cargo-target/ip/release/libip_audit.a
    output=/work/work/analysis/iproute2-7.3.0/routel-frontend
    test -f "$archive"
    clang-18 -std=c11 -O2 -g -Wall -Wextra -Werror \
      -ffunction-sections -fdata-sections -Wl,--gc-sections \
      /work/bridges/iproute2_routel.c "$archive" \
      -ltirpc -lbpf -lelf -lmnl -lcap -ldl -lpthread -lm \
      -o "$output/routel-real"
    nm -g --defined-only "$output/routel-real" >"$output/routel-real.symbols"
    test "$(awk '\''$NF == "rustbox_iproute2_routel_main" { n++ } END { print n+0 }'\'' \
      "$output/routel-real.symbols")" -eq 1
    python3 -B /work/tests/iproute2-routel-real.py \
      --canonical /work/work/upstream/iproute2-7.3.0/ip/routel \
      --canonical-ip-directory /rustbox-iproute2/programs-gcc \
      --native "$output/routel-real" \
      --output "$output/real-differential.json"
    valgrind --leak-check=full --show-leak-kinds=all \
      --errors-for-leak-kinds=definite,indirect,possible \
      --error-exitcode=99 --log-file="$output/valgrind-real.log" \
      "$output/routel-real" all >"$output/valgrind-real.out"
    grep -q "ERROR SUMMARY: 0 errors" "$output/valgrind-real.log"
    grep -Eq "All heap blocks were freed|definitely lost: 0 bytes" \
      "$output/valgrind-real.log"
    grep -Eq "All heap blocks were freed|indirectly lost: 0 bytes" \
      "$output/valgrind-real.log"
    grep -Eq "All heap blocks were freed|possibly lost: 0 bytes" \
      "$output/valgrind-real.log"
    chmod -R a+rwX "$output"
  '
