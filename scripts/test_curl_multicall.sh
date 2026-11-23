#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-curl:2026-11-23 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    rustbox=/rustbox-coreutils/canonical-clang-no-security-compdb/src/rustbox
    canonical=/work/work/analysis/curl-8.23.0/oracle
    output=/work/work/analysis/curl-8.23.0/multicall
    dispatch=/rustbox-curl/multicall-dispatch
    rm -rf "$output" "$dispatch"
    mkdir -p "$output" "$dispatch"
    ln -s "$rustbox" "$dispatch/curl"
    ln -s "$rustbox" "$dispatch/curl-config"

    python3 /work/tests/curl-oracle-differential.py \
      --gcc "$canonical/curl-gcc" --clang "$dispatch/curl" \
      --output "$output/differential.json"
    python3 /work/tests/curl-config-frontend.py \
      --canonical "$canonical/curl-config-clang" \
      --native "$dispatch/curl-config" \
      --output "$output/curl-config-differential.json"

    "$rustbox" curl --version >"$output/direct-curl-version.out"
    "$rustbox" curl-config --version >"$output/direct-curl-config-version.out"
    cmp "$output/direct-curl-version.out" "$canonical/version-clang.txt"
    printf "libcurl 8.23.0\n" >"$output/curl-config-version.expected"
    cmp "$output/direct-curl-config-version.out" \
      "$output/curl-config-version.expected"

    valgrind --leak-check=full --show-leak-kinds=all \
      --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
      --log-file="$output/valgrind-version.log" \
      "$dispatch/curl" --version >"$output/valgrind-version.out"
    printf "rustbox-curl-multicall-payload\n" >"$output/file-input"
    valgrind --leak-check=full --show-leak-kinds=all \
      --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
      --log-file="$output/valgrind-file.log" \
      "$dispatch/curl" --silent --show-error \
        "file://$output/file-input" >"$output/valgrind-file.out"
    cmp "$output/file-input" "$output/valgrind-file.out"
    for operation in version file; do
      grep -q "ERROR SUMMARY: 0 errors" "$output/valgrind-$operation.log"
      if ! grep -q "All heap blocks were freed -- no leaks are possible" \
          "$output/valgrind-$operation.log"; then
        grep -q "definitely lost: 0 bytes in 0 blocks" \
          "$output/valgrind-$operation.log"
        grep -q "indirectly lost: 0 bytes in 0 blocks" \
          "$output/valgrind-$operation.log"
        grep -q "possibly lost: 0 bytes in 0 blocks" \
          "$output/valgrind-$operation.log"
      fi
    done
  '
