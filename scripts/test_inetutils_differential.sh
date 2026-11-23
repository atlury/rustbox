#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-inetutils:2026-11-23 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    output=/work/work/analysis/inetutils-2.8/oracle
    python3 /work/tests/inetutils-oracle-differential.py \
      --gcc-root /rustbox-inetutils/oracle-gcc \
      --clang-root /rustbox-inetutils/oracle-clang \
      --output "$output/differential.json"
    for item in \
      hostname:src/hostname \
      dnsdomainname:src/dnsdomainname \
      ifconfig:ifconfig/ifconfig \
      whois:whois/whois
    do
      name=${item%%:*}
      relative=${item#*:}
      valgrind --leak-check=full --show-leak-kinds=all \
        --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
        --log-file="$output/valgrind-$name.log" \
        "/rustbox-inetutils/oracle-gcc/$relative" --version \
        >"$output/valgrind-$name.out"
      grep -q "ERROR SUMMARY: 0 errors" "$output/valgrind-$name.log"
    done
  '
