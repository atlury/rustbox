#!/bin/sh
# SPDX-License-Identifier: ISC
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
"$root/scripts/normalize_pkgconf.sh"
RUSTBOX_TOOL_IMAGE=rustbox-normalize:2026-11-19 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    readonly volume=/rustbox-pkgconf
    readonly source=$volume/normalized-source
    readonly gcc_build=$volume/normalized-gcc-static
    readonly clang_build=$volume/normalized-clang-static
    readonly sanitizer_build=$volume/normalized-sanitizer-shared
    readonly output=/work/work/analysis/pkgconf-3.0.11/normalized

    rm -rf "$gcc_build" "$clang_build" "$sanitizer_build"
    mkdir -p "$output"

    CC=gcc meson setup "$gcc_build" "$source" \
      --buildtype=debugoptimized --default-library=static -Db_lto=false
    meson compile -C "$gcc_build" -j "$(nproc)"
    meson test -C "$gcc_build" --num-processes "$(nproc)" --print-errorlogs
    cp "$gcc_build/meson-logs/testlog.json" "$output/gcc-testlog.json"

    CC=clang-18 meson setup "$clang_build" "$source" \
      --buildtype=debugoptimized --default-library=static -Db_lto=false
    meson compile -C "$clang_build" -j "$(nproc)"
    meson test -C "$clang_build" --num-processes "$(nproc)" --print-errorlogs
    cp "$clang_build/meson-logs/testlog.json" "$output/clang-testlog.json"

    CC=gcc meson setup "$sanitizer_build" "$source" \
      --buildtype=debug -Db_sanitize=address,undefined -Db_lundef=false \
      --default-library=shared -Db_lto=false
    meson compile -C "$sanitizer_build" -j "$(nproc)"
    ASAN_OPTIONS=detect_leaks=1:halt_on_error=1 \
    UBSAN_OPTIONS=halt_on_error=1 \
      meson test -C "$sanitizer_build" --num-processes "$(nproc)" --print-errorlogs
    cp "$sanitizer_build/meson-logs/testlog.json" "$output/sanitizer-testlog.json"

    meson test -C "$gcc_build" --num-processes 1 --print-errorlogs \
      --wrapper="valgrind --leak-check=full --show-leak-kinds=all --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99" \
      >"$output/valgrind-test.log" 2>&1
    cp "$gcc_build/meson-logs/testlog-valgrind.txt" "$output/valgrind-testlog.txt"

    cp "$gcc_build/compile_commands.json" "$output/gcc-compile-commands.json"
    cp "$clang_build/compile_commands.json" "$output/clang-compile-commands.json"
    cp "$sanitizer_build/compile_commands.json" "$output/sanitizer-compile-commands.json"
    for compiler in gcc clang; do
      build=$volume/normalized-$compiler-static
      for tool in pkgconf bomtool pccritic spdxtool; do
        cp "$build/$tool" "$output/$tool-$compiler"
      done
    done
  '
