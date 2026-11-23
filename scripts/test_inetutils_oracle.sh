#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-inetutils:2026-11-23 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    output=/work/work/analysis/inetutils-2.8/oracle
    run_suite()
    {
      build=$1
      compiler=$2
      set +e
      make -C "$build" -j"$(nproc)" check >"$output/$compiler-test.log" 2>&1
      status=$?
      set -e
      printf "%s\n" "$status" >"$output/$compiler-test.status"
      cp "$build/tests/test-suite.log" "$output/$compiler-test-suite.log"
    }
    run_suite /rustbox-inetutils/oracle-gcc gcc
    run_suite /rustbox-inetutils/oracle-clang clang
  '
