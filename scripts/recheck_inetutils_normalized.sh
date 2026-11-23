#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
"$root/scripts/normalize_inetutils.sh"
RUSTBOX_TOOL_IMAGE=rustbox-inetutils:2026-11-23 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    release=/work/work/normalized/inetutils-2.8
    volume=/rustbox-inetutils
    source=$volume/normalized-source
    output=/work/work/analysis/inetutils-2.8/normalized
    cp -a "$release/." "$source/"
    for compiler in gcc clang; do
      build=$volume/normalized-$compiler
      make -C "$build" -j"$(nproc)" >"$output/$compiler-recheck-build.log" 2>&1
      set +e
      make -C "$build" -j"$(nproc)" check >"$output/$compiler-test.log" 2>&1
      status=$?
      set -e
      printf "%s\n" "$status" >"$output/$compiler-test.status"
      cp "$build/tests/test-suite.log" "$output/$compiler-test-suite.log"
    done
    python3 /work/tests/inetutils-oracle-differential.py \
      --gcc-root "$volume/oracle-gcc" --clang-root "$volume/normalized-gcc" \
      --output "$output/gcc-differential.json"
    python3 /work/tests/inetutils-oracle-differential.py \
      --gcc-root "$volume/oracle-clang" --clang-root "$volume/normalized-clang" \
      --output "$output/clang-differential.json"
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
        "$volume/normalized-gcc/$relative" --version \
        >"$output/valgrind-$name.out"
      grep -q "ERROR SUMMARY: 0 errors" "$output/valgrind-$name.log"
    done
    chmod -R a+rwX "$source" "$volume/normalized-gcc" \
      "$volume/normalized-clang" "$output"
  '
