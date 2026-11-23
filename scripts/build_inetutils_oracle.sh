#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-inetutils:2026-11-23 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    export PYTHONDONTWRITEBYTECODE=1
    source=/work/work/upstream/inetutils-2.8
    volume=/rustbox-inetutils
    output=/work/work/analysis/inetutils-2.8/oracle

    configure_build()
    {
      build=$1
      compiler=$2
      mkdir -p "$build"
      cd "$build"
      CC="$compiler" CFLAGS="-O2 -g -fno-omit-frame-pointer" \
        "$source/configure" \
          --disable-dependency-tracking \
          --disable-systemd \
          --without-pam \
          --without-wrap \
          --without-krb4 \
          --without-krb5 \
          --without-shishi \
          --without-idn
      bear --output compile_commands.json -- make -j"$(nproc)"
    }

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

    rm -rf "$output" "$volume/oracle-gcc" "$volume/oracle-clang"
    mkdir -p "$output"
    configure_build "$volume/oracle-gcc" gcc >"$output/gcc-build.log" 2>&1
    configure_build "$volume/oracle-clang" clang-18 >"$output/clang-build.log" 2>&1

    cp "$volume/oracle-gcc/compile_commands.json" "$output/gcc-compile-commands.json"
    cp "$volume/oracle-clang/compile_commands.json" "$output/clang-compile-commands.json"
    run_suite "$volume/oracle-gcc" gcc
    run_suite "$volume/oracle-clang" clang
  '
