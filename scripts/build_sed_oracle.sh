#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-sed:2026-11-20 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    release=/work/work/upstream/sed-4.10
    volume=/rustbox-sed
    source=$volume/source
    output=/work/work/analysis/sed-4.10/oracle
    gcc_build=$volume/oracle-gcc
    clang_build=$volume/oracle-clang
    sanitizer_build=$volume/oracle-sanitizer

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

    rm -rf "$output" "$source" "$gcc_build" "$clang_build" "$sanitizer_build"
    mkdir -p "$output" "$source" "$gcc_build" "$clang_build" "$sanitizer_build"
    cp -a "$release/." "$source/"

    cd "$gcc_build"
    CC=gcc CFLAGS="-O2 -g -fno-omit-frame-pointer" \
      "$source/configure" --disable-dependency-tracking --without-selinux
    bear --output compile_commands.json -- make -j"$(nproc)"
    chown -R nobody:nogroup "$gcc_build"
    run_logged "$output/gcc-check.log" \
      runuser --user=nobody -- make -j"$(nproc)" check

    cd "$clang_build"
    CC=clang-18 CFLAGS="-O2 -g -fno-omit-frame-pointer" \
      "$source/configure" --disable-dependency-tracking --without-selinux
    bear --output compile_commands.json -- make -j"$(nproc)"
    chown -R nobody:nogroup "$clang_build"
    run_logged "$output/clang-check.log" \
      runuser --user=nobody -- make -j"$(nproc)" check

    cd "$sanitizer_build"
    CC=gcc CFLAGS="-O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer" \
      LDFLAGS="-fsanitize=address,undefined" \
      "$source/configure" --disable-dependency-tracking --without-selinux
    bear --force-wrapper --output compile_commands.json -- make -j"$(nproc)"
    chown -R nobody:nogroup "$sanitizer_build"
    run_logged "$output/sanitizer-check.log" \
      runuser --user=nobody -- env \
        ASAN_OPTIONS=detect_leaks=0:halt_on_error=1 \
        UBSAN_OPTIONS=halt_on_error=1 \
        make -j"$(nproc)" check-TESTS

    printf "alpha old\nbeta old\n" > "$output/valgrind-input"
    valgrind --leak-check=full --show-leak-kinds=all \
      --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
      --log-file="$output/valgrind.log" \
      "$gcc_build/sed/sed" -n -e p "$output/valgrind-input" \
      > "$output/valgrind.out"
    grep -q "ERROR SUMMARY: 0 errors" "$output/valgrind.log"
    grep -q "definitely lost: 0 bytes in 0 blocks" "$output/valgrind.log"
    grep -q "indirectly lost: 0 bytes in 0 blocks" "$output/valgrind.log"
    grep -q "possibly lost: 0 bytes in 0 blocks" "$output/valgrind.log"

    cp "$gcc_build/compile_commands.json" "$output/gcc-compile-commands.json"
    cp "$clang_build/compile_commands.json" "$output/clang-compile-commands.json"
    cp "$sanitizer_build/compile_commands.json" "$output/sanitizer-compile-commands.json"
    cp "$gcc_build/sed/sed" "$output/sed-gcc"
    cp "$clang_build/sed/sed" "$output/sed-clang"
    cp "$gcc_build/config.h" "$output/config-gcc.h"
    cp "$clang_build/config.h" "$output/config-clang.h"
    cp "$gcc_build/sed/version.c" "$output/version.c"
    readelf -d "$output/sed-gcc" > "$output/sed-gcc.dynamic"
    readelf -d "$output/sed-clang" > "$output/sed-clang.dynamic"
  '

