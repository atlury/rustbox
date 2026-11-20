#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-normalize:2026-11-19 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    readonly release=/work/work/upstream/m4-1.4.21
    readonly volume=/rustbox-m4
    readonly source=$volume/source
    readonly gcc_build=$volume/canonical-gcc
    readonly clang_build=$volume/canonical-clang
    readonly sanitizer_build=$volume/canonical-sanitizer
    readonly evidence=/work/work/analysis/m4-1.4.21/oracle

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

    rm -rf "$source" "$gcc_build" "$clang_build" "$sanitizer_build"
    mkdir -p "$volume" "$evidence"
    cp -a "$release" "$source"

    mkdir "$gcc_build"
    cd "$gcc_build"
    CC=gcc CFLAGS="-O2 -g -fno-omit-frame-pointer" \
      "$source/configure" --disable-dependency-tracking
    bear --output compile_commands.json -- make -j"$(nproc)"
    run_logged "$volume/gcc-check.log" make -j"$(nproc)" check

    mkdir "$clang_build"
    cd "$clang_build"
    CC=clang-18 CFLAGS="-O2 -g -fno-omit-frame-pointer" \
      "$source/configure" --disable-dependency-tracking
    bear --output compile_commands.json -- make -j"$(nproc)"
    run_logged "$volume/clang-check.log" make -j"$(nproc)" check

    mkdir "$sanitizer_build"
    cd "$sanitizer_build"
    CC=gcc \
      CFLAGS="-O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer" \
      LDFLAGS="-fsanitize=address,undefined" \
      "$source/configure" --disable-dependency-tracking
    make -j"$(nproc)"
    cd "$sanitizer_build/checks"
    PATH="$sanitizer_build/src:$PATH"
    export PATH
    ASAN_OPTIONS=detect_leaks=1:halt_on_error=1
    UBSAN_OPTIONS=halt_on_error=1
    export ASAN_OPTIONS UBSAN_OPTIONS
    run_logged "$volume/sanitizer-check.log" \
      "$source/checks/check-them" -I "$source/examples" \
      "$source"/checks/*[0-9][0-9][0-9].*

    printf "define(\`twice\047, \`\$1\$1\047)dnl\ntwice(\`rustbox\047)\n" \
      > "$volume/valgrind.m4"
    valgrind --leak-check=full --show-leak-kinds=all \
      --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
      --log-file="$volume/valgrind.log" \
      "$gcc_build/src/m4" "$volume/valgrind.m4" > "$volume/valgrind.out"
    test "$(cat "$volume/valgrind.out")" = rustboxrustbox

    cp "$gcc_build/compile_commands.json" "$evidence/gcc-compile-commands.json"
    cp "$clang_build/compile_commands.json" "$evidence/clang-compile-commands.json"
    cp "$gcc_build/tests/test-suite.log" "$evidence/gcc-test-suite.log"
    cp "$clang_build/tests/test-suite.log" "$evidence/clang-test-suite.log"
    cp "$volume/gcc-check.log" "$evidence/gcc-check.log"
    cp "$volume/clang-check.log" "$evidence/clang-check.log"
    cp "$volume/sanitizer-check.log" "$evidence/sanitizer-check.log"
    cp "$volume/valgrind.log" "$evidence/valgrind.log"
    cp "$gcc_build/src/m4" "$evidence/m4-gcc"
    cp "$clang_build/src/m4" "$evidence/m4-clang"
  '
