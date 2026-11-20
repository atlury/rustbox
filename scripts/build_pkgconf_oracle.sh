#!/bin/sh
# SPDX-License-Identifier: ISC
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-normalize:2026-11-19 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    readonly release=/work/work/upstream/pkgconf-3.0.11
    readonly volume=/rustbox-pkgconf
    readonly source=$volume/source
    readonly gcc_build=$volume/canonical-gcc-static
    readonly clang_build=$volume/canonical-clang-static
    readonly sanitizer_build=$volume/canonical-sanitizer-shared
    readonly evidence=/work/work/analysis/pkgconf-3.0.11/oracle

    rm -rf "$source" "$gcc_build" "$clang_build" "$sanitizer_build" "$evidence"
    mkdir -p "$source" "$evidence"
    cp -a "$release/." "$source/"
    rm -rf "$source/.git"

    CC=gcc meson setup "$gcc_build" "$source" \
      --buildtype=debugoptimized --default-library=static -Db_lto=false
    meson compile -C "$gcc_build" -j "$(nproc)"
    meson test -C "$gcc_build" --num-processes "$(nproc)" --print-errorlogs

    CC=clang-18 meson setup "$clang_build" "$source" \
      --buildtype=debugoptimized --default-library=static -Db_lto=false
    meson compile -C "$clang_build" -j "$(nproc)"
    meson test -C "$clang_build" --num-processes "$(nproc)" --print-errorlogs

    CC=gcc meson setup "$sanitizer_build" "$source" \
      --buildtype=debug -Db_sanitize=address,undefined -Db_lundef=false \
      --default-library=shared -Db_lto=false
    meson compile -C "$sanitizer_build" -j "$(nproc)"
    ASAN_OPTIONS=detect_leaks=1:halt_on_error=1 \
    UBSAN_OPTIONS=halt_on_error=1 \
      meson test -C "$sanitizer_build" --num-processes "$(nproc)" --print-errorlogs

    cp "$gcc_build/compile_commands.json" "$evidence/gcc-compile-commands.json"
    cp "$clang_build/compile_commands.json" "$evidence/clang-compile-commands.json"
    cp "$sanitizer_build/compile_commands.json" "$evidence/sanitizer-compile-commands.json"
    cp "$gcc_build/meson-logs/testlog.json" "$evidence/gcc-testlog.json"
    cp "$clang_build/meson-logs/testlog.json" "$evidence/clang-testlog.json"
    cp "$sanitizer_build/meson-logs/testlog.json" "$evidence/sanitizer-testlog.json"
    for compiler in gcc clang; do
      build=$volume/canonical-$compiler-static
      for tool in pkgconf bomtool pccritic spdxtool; do
        cp "$build/$tool" "$evidence/$tool-$compiler"
      done
    done
  '
