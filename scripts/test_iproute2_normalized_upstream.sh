#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
exec docker run --rm --platform linux/amd64 --privileged \
  --volume "$root:/work" \
  --volume rustbox-iproute2-7.3.0:/rustbox-iproute2 \
  --workdir /work \
  rustbox-iproute2:2026-11-24 sh -eu -c '
    output=/work/work/analysis/iproute2-7.3.0/normalized
    mkdir -p /rustbox-iproute2/test-bin
    ln -sf /work/tools/iproute2-sudo /rustbox-iproute2/test-bin/sudo
    export PATH=/rustbox-iproute2/test-bin:$PATH
    for compiler in gcc clang-18; do
      build=/rustbox-iproute2/normalized-$compiler
      make -C "$build/testsuite" clean >/dev/null 2>&1 || true
      status_file=$(mktemp)
      set +e
      (make -C "$build" SHARED_LIBS=n check; printf "%s\n" "$?" >"$status_file") \
        2>&1 | cat >"$output/$compiler-privileged-test.log"
      status=$(cat "$status_file")
      set -e
      rm -f "$status_file"
      printf "%s\n" "$status" >"$output/$compiler-privileged-test.status"
    done
    chmod -R a+rwX "$output"
  '
