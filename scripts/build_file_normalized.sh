#!/bin/sh
# SPDX-License-Identifier: BSD-2-Clause
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
"$root/scripts/normalize_file.sh"
RUSTBOX_TOOL_IMAGE=rustbox-file:2026-11-20 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    readonly volume=/rustbox-file
    readonly source=$volume/normalized-source
    readonly gcc_build=$volume/normalized-gcc
    readonly clang_build=$volume/normalized-clang
    readonly sanitizer_build=$volume/normalized-sanitizer
    readonly output=/work/work/analysis/file-5.48/normalized

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

    rm -rf "$gcc_build" "$clang_build" "$sanitizer_build"
    mkdir -p "$output"

    mkdir "$gcc_build"
    cd "$gcc_build"
    CC=gcc CFLAGS="-O2 -g -fno-omit-frame-pointer" \
      "$source/configure" --disable-dependency-tracking \
      --disable-shared --enable-static
    bear --output compile_commands.json -- make -j"$(nproc)"
    run_logged "$output/gcc-check.log" make -j"$(nproc)" check

    mkdir "$clang_build"
    cd "$clang_build"
    CC=clang-18 CFLAGS="-O2 -g -fno-omit-frame-pointer" \
      "$source/configure" --disable-dependency-tracking \
      --disable-shared --enable-static
    bear --output compile_commands.json -- make -j"$(nproc)"
    run_logged "$output/clang-check.log" make -j"$(nproc)" check

    mkdir "$sanitizer_build"
    cd "$sanitizer_build"
    CC=gcc CFLAGS="-O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer" \
      LDFLAGS="-fsanitize=address,undefined" \
      "$source/configure" --disable-dependency-tracking \
      --disable-shared --enable-static --disable-libseccomp --disable-landlock
    bear --force-wrapper --output compile_commands.json -- make -j"$(nproc)"
    ASAN_OPTIONS=detect_leaks=1:halt_on_error=1 \
    UBSAN_OPTIONS=halt_on_error=1 \
      run_logged "$output/sanitizer-check.log" make -j"$(nproc)" check

    printf "rustbox normalized file\n" > "$volume/normalized-valgrind-input.txt"
    valgrind --leak-check=full --show-leak-kinds=all \
      --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
      --log-file="$output/valgrind.log" \
      "$gcc_build/src/file" --no-sandbox -m "$gcc_build/magic/magic" \
      "$volume/normalized-valgrind-input.txt" > "$output/valgrind.out"
    grep -q "ERROR SUMMARY: 0 errors" "$output/valgrind.log"
    grep -q "All heap blocks were freed -- no leaks are possible" "$output/valgrind.log"

    cp "$gcc_build/compile_commands.json" "$output/gcc-compile-commands.json"
    cp "$clang_build/compile_commands.json" "$output/clang-compile-commands.json"
    cp "$sanitizer_build/compile_commands.json" "$output/sanitizer-compile-commands.json"
    cp "$gcc_build/src/file" "$output/file-gcc"
    cp "$clang_build/src/file" "$output/file-clang"
    cp "$gcc_build/src/.libs/libmagic.a" "$output/libmagic-gcc.a"
    cp "$clang_build/src/.libs/libmagic.a" "$output/libmagic-clang.a"
    cp "$gcc_build/config.h" "$output/config-gcc.h"
    cp "$clang_build/config.h" "$output/config-clang.h"
    cp "$gcc_build/magic/magic.mgc" "$output/magic-gcc.mgc"
    cp "$clang_build/magic/magic.mgc" "$output/magic-clang.mgc"

    python3 /work/tests/file-oracle-differential.py \
      --gcc /rustbox-file/canonical-gcc/src/file \
      --clang "$gcc_build/src/file" \
      --magic /rustbox-file/canonical-gcc/magic/magic \
      --upstream-tests "$source/tests" \
      --output "$output/canonical-normalized-gcc-differential.json"
    python3 /work/tests/file-oracle-differential.py \
      --gcc /rustbox-file/canonical-clang/src/file \
      --clang "$clang_build/src/file" \
      --magic /rustbox-file/canonical-clang/magic/magic \
      --upstream-tests "$source/tests" \
      --output "$output/canonical-normalized-clang-differential.json"
  '
