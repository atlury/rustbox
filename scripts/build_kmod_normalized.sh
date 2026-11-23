#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
"$root/scripts/normalize_kmod.sh"
RUSTBOX_TOOL_IMAGE=rustbox-kmod:2026-11-24 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    release=/work/work/normalized/kmod-34.3
    volume=/rustbox-kmod
    source=$volume/normalized-source
    output=/work/work/analysis/kmod-34.3/normalized
    oracle=/work/work/analysis/kmod-34.3/oracle
    rm -rf "$source" "$volume/normalized-gcc" "$volume/normalized-clang" "$output"
    mkdir -p "$source" "$output"
    cp -a "$release/." "$source/"

    build_one()
    {
      compiler=$1
      cc=$2
      build=$volume/normalized-$compiler
      CC="$cc" meson setup "$build" "$source" \
        --buildtype=debugoptimized \
        -Dbuild-tests=true -Dmanpages=false -Ddocs=false \
        -Dbashcompletiondir=no -Dfishcompletiondir=no -Dzshcompletiondir=no \
        -Ddlopen=[] -Dzstd=enabled -Dxz=enabled -Dzlib=enabled \
        -Dopenssl=enabled -Dlogging=true >"$output/$compiler-build.log" 2>&1
      kdir=$(find /usr/src -mindepth 1 -maxdepth 1 -type d \
        -name "linux-headers-*-generic" | sort | tail -n 1)
      KDIR="$kdir" meson compile -C "$build" -j"$(nproc)" \
        >>"$output/$compiler-build.log" 2>&1
      cp "$build/compile_commands.json" "$output/$compiler-compile-commands.json"
      KDIR="$kdir" meson test -C "$build" --print-errorlogs \
        >"$output/$compiler-test.log" 2>&1
      cp "$build/meson-logs/testlog.json" "$output/$compiler-testlog.json"
    }

    build_one gcc gcc
    build_one clang clang-18
    python3 /work/tests/kmod-oracle-differential.py \
      --gcc-root "$volume/oracle-gcc" --clang-root "$volume/normalized-gcc" \
      --output "$output/gcc-differential.json"
    python3 /work/tests/kmod-oracle-differential.py \
      --gcc-root "$volume/oracle-clang" --clang-root "$volume/normalized-clang" \
      --output "$output/clang-differential.json"
    for name in kmod depmod insmod lsmod modinfo modprobe rmmod; do
      valgrind --leak-check=full --show-leak-kinds=all \
        --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
        --log-file="$output/valgrind-$name.log" \
        "$volume/normalized-gcc/$name" --version >"$output/valgrind-$name.out"
      grep -q "ERROR SUMMARY: 0 errors" "$output/valgrind-$name.log"
    done
    test "$(nm -g --defined-only "$volume/normalized-gcc/kmod.p/tools_kmod.c.o" | \
      grep -c " rustbox_kmod_main$")" -eq 1
    chmod -R a+rwX "$source" "$volume/normalized-gcc" \
      "$volume/normalized-clang" "$output"
  '
