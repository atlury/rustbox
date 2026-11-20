#!/bin/sh
# SPDX-License-Identifier: BSD-2-Clause
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-file:2026-11-20 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    readonly release=/work/work/upstream/file-5.48
    readonly volume=/rustbox-file
    readonly source=$volume/source
    readonly gcc_build=$volume/canonical-gcc
    readonly clang_build=$volume/canonical-clang
    readonly sanitizer_build=$volume/canonical-sanitizer
    readonly evidence=/work/work/analysis/file-5.48/oracle

    run_logged()
    {
      log=$1
      shift
      if "$@" >"$log" 2>&1; then
        cat "$log"
      else
        status=$?
        cat "$log"
        return "$status"
      fi
    }

    rm -rf "$source" "$gcc_build" "$clang_build" "$sanitizer_build" "$evidence"
    mkdir -p "$source" "$evidence"
    cp -a "$release/." "$source/"

    mkdir "$gcc_build"
    cd "$gcc_build"
    CC=gcc CFLAGS="-O2 -g -fno-omit-frame-pointer" \
      "$source/configure" --disable-dependency-tracking \
      --disable-shared --enable-static
    bear --output compile_commands.json -- make -j"$(nproc)"
    run_logged "$evidence/gcc-check.log" make -j"$(nproc)" check

    mkdir "$clang_build"
    cd "$clang_build"
    CC=clang-18 CFLAGS="-O2 -g -fno-omit-frame-pointer" \
      "$source/configure" --disable-dependency-tracking \
      --disable-shared --enable-static
    bear --output compile_commands.json -- make -j"$(nproc)"
    run_logged "$evidence/clang-check.log" make -j"$(nproc)" check

    mkdir "$sanitizer_build"
    cd "$sanitizer_build"
    CC=gcc CFLAGS="-O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer" \
      LDFLAGS="-fsanitize=address,undefined" \
      "$source/configure" --disable-dependency-tracking \
      --disable-shared --enable-static --disable-libseccomp --disable-landlock
    bear --force-wrapper --output compile_commands.json -- make -j"$(nproc)"
    ASAN_OPTIONS=detect_leaks=1:halt_on_error=1 \
    UBSAN_OPTIONS=halt_on_error=1 \
      run_logged "$evidence/sanitizer-check.log" make -j"$(nproc)" check

    printf "rustbox file oracle\n" > "$volume/valgrind-input.txt"
    valgrind --leak-check=full --show-leak-kinds=all \
      --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
      --log-file="$evidence/valgrind.log" \
      "$gcc_build/src/file" --no-sandbox -m "$gcc_build/magic/magic" \
      "$volume/valgrind-input.txt" \
      > "$evidence/valgrind.out"
    grep -q "ERROR SUMMARY: 0 errors" "$evidence/valgrind.log"
    grep -q "All heap blocks were freed -- no leaks are possible" "$evidence/valgrind.log"

    cp "$gcc_build/compile_commands.json" "$evidence/gcc-compile-commands.json"
    cp "$clang_build/compile_commands.json" "$evidence/clang-compile-commands.json"
    cp "$sanitizer_build/compile_commands.json" "$evidence/sanitizer-compile-commands.json"
    cp "$gcc_build/src/file" "$evidence/file-gcc"
    cp "$clang_build/src/file" "$evidence/file-clang"
    cp "$gcc_build/src/.libs/libmagic.a" "$evidence/libmagic-gcc.a"
    cp "$clang_build/src/.libs/libmagic.a" "$evidence/libmagic-clang.a"
    cp "$gcc_build/config.h" "$evidence/config-gcc.h"
    cp "$clang_build/config.h" "$evidence/config-clang.h"
    cp "$gcc_build/magic/magic.mgc" "$evidence/magic-gcc.mgc"
    cp "$clang_build/magic/magic.mgc" "$evidence/magic-clang.mgc"
  '
