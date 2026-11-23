#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-kmod:2026-11-24 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    export PYTHONDONTWRITEBYTECODE=1
    source=/work/work/upstream/kmod-34.3
    volume=/rustbox-kmod
    output=/work/work/analysis/kmod-34.3/oracle

    configure_build()
    {
      build=$1
      compiler=$2
      CC="$compiler" meson setup "$build" "$source" \
        --buildtype=debugoptimized \
        -Dbuild-tests=true -Dmanpages=false -Ddocs=false \
        -Dbashcompletiondir=no -Dfishcompletiondir=no -Dzshcompletiondir=no \
        -Ddlopen=[] -Dzstd=enabled -Dxz=enabled -Dzlib=enabled \
        -Dopenssl=enabled -Dlogging=true
      kdir=$(find /usr/src -mindepth 1 -maxdepth 1 -type d \
        -name "linux-headers-*-generic" | sort | tail -n 1)
      test -n "$kdir"
      KDIR="$kdir" meson compile -C "$build" -j"$(nproc)"
    }

    run_suite()
    {
      build=$1
      compiler=$2
      kdir=$(find /usr/src -mindepth 1 -maxdepth 1 -type d \
        -name "linux-headers-*-generic" | sort | tail -n 1)
      test -n "$kdir"
      set +e
      KDIR="$kdir" meson test -C "$build" --print-errorlogs \
        >"$output/$compiler-test.log" 2>&1
      status=$?
      set -e
      printf "%s\n" "$status" >"$output/$compiler-test.status"
      cp "$build/meson-logs/testlog.json" "$output/$compiler-testlog.json"
    }

    rm -rf "$output" "$volume/oracle-gcc" "$volume/oracle-clang"
    mkdir -p "$output"
    configure_build "$volume/oracle-gcc" gcc >"$output/gcc-build.log" 2>&1
    configure_build "$volume/oracle-clang" clang-18 >"$output/clang-build.log" 2>&1
    cp "$volume/oracle-gcc/compile_commands.json" "$output/gcc-compile-commands.json"
    cp "$volume/oracle-clang/compile_commands.json" "$output/clang-compile-commands.json"
    run_suite "$volume/oracle-gcc" gcc
    run_suite "$volume/oracle-clang" clang
    for compiler in gcc clang; do
      build=$volume/oracle-$compiler
      cp "$build/kmod" "$output/kmod-$compiler"
      readelf -d "$build/kmod" >"$output/$compiler-dynamic.txt"
      "$build/kmod" --version >"$output/$compiler-version.txt"
    done
    cmp "$output/gcc-version.txt" "$output/clang-version.txt"
  '
