#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
exec docker run --rm --platform linux/amd64 --privileged \
  --volume "$root:/work" \
  --volume rustbox-e2fsprogs-1.47.4:/rustbox-e2fsprogs \
  --workdir /work rustbox-e2fsprogs:2026-11-24 sh -eu -c '
    evidence=/work/work/analysis/e2fsprogs-1.47.4/normalization
    run_suite()
    {
      compiler=$1
      build=/rustbox-e2fsprogs/normalized-$compiler
      set +e
      make -C "$build" check >"$evidence/$compiler-test.log" 2>&1
      status=$?
      set -e
      printf "%s\n" "$status" >"$evidence/$compiler-test.status"
    }
    run_suite gcc &
    gcc_pid=$!
    run_suite clang-18 &
    clang_pid=$!
    wait "$gcc_pid"
    wait "$clang_pid"
    chmod -R a+rwX "$evidence"
  '
