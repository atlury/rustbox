#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-diffutils:2026-11-20 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    release=/work/work/upstream/diffutils-3.12
    volume=/rustbox-diffutils
    source=$volume/source
    output=/work/work/analysis/diffutils-3.12/oracle
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
      "$source/configure" --disable-dependency-tracking
    bear --output compile_commands.json -- make -j"$(nproc)"
    chown -R nobody:nogroup "$gcc_build"
    run_logged "$output/gcc-check.log" \
      runuser --user=nobody -- make -j"$(nproc)" check

    cd "$clang_build"
    CC=clang-18 CFLAGS="-O2 -g -fno-omit-frame-pointer" \
      "$source/configure" --disable-dependency-tracking
    bear --output compile_commands.json -- make -j"$(nproc)"
    chown -R nobody:nogroup "$clang_build"
    run_logged "$output/clang-check.log" \
      runuser --user=nobody -- make -j"$(nproc)" check

    cd "$sanitizer_build"
    CC=gcc CFLAGS="-O1 -g -fsanitize=address,undefined -fno-sanitize=nonnull-attribute -fno-omit-frame-pointer" \
      LDFLAGS="-fsanitize=address,undefined" \
      "$source/configure" --disable-dependency-tracking
    bear --force-wrapper --output compile_commands.json -- make -j"$(nproc)"
    chown -R nobody:nogroup "$sanitizer_build"
    run_logged "$output/sanitizer-check.log" \
      runuser --user=nobody -- env \
        ASAN_OPTIONS=detect_leaks=0:halt_on_error=1:allocator_may_return_null=1 \
        UBSAN_OPTIONS=halt_on_error=1 \
        make -j"$(nproc)" check

    printf "alpha\nbeta\ngamma\n" > "$output/left"
    printf "alpha\nBETA\ngamma\n" > "$output/right"
    for utility in cmp diff diff3 sdiff; do
      case $utility in
        cmp|diff) arguments="$output/left $output/right" ;;
        diff3) arguments="$output/left $output/right $output/left" ;;
        sdiff) arguments="--help" ;;
      esac
      valgrind --leak-check=full --show-leak-kinds=all \
        --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
        --log-file="$output/valgrind-$utility.log" \
        "$gcc_build/src/$utility" $arguments > "$output/valgrind-$utility.out" || status=$?
      if test "$utility" = diff3; then
        test "${status:-0}" -eq 99
        grep -q "ERROR SUMMARY: 2 errors" "$output/valgrind-$utility.log"
        grep -q "definitely lost: 4,096 bytes in 1 blocks" "$output/valgrind-$utility.log"
        grep -q "possibly lost: 4,096 bytes in 1 blocks" "$output/valgrind-$utility.log"
      else
        test "${status:-0}" -le 1
        grep -q "ERROR SUMMARY: 0 errors" "$output/valgrind-$utility.log"
        grep -q "definitely lost: 0 bytes in 0 blocks" "$output/valgrind-$utility.log"
        grep -q "possibly lost: 0 bytes in 0 blocks" "$output/valgrind-$utility.log"
      fi
      unset status
      grep -q "indirectly lost: 0 bytes in 0 blocks" "$output/valgrind-$utility.log"
    done

    cp "$gcc_build/compile_commands.json" "$output/gcc-compile-commands.json"
    cp "$clang_build/compile_commands.json" "$output/clang-compile-commands.json"
    cp "$sanitizer_build/compile_commands.json" "$output/sanitizer-compile-commands.json"
    cp "$gcc_build/lib/config.h" "$output/config-gcc.h"
    cp "$clang_build/lib/config.h" "$output/config-clang.h"
    cmp "$gcc_build/src/version.c" "$clang_build/src/version.c"
    cp "$gcc_build/src/version.c" "$output/version.c"
    for utility in cmp diff diff3 sdiff; do
      cp "$gcc_build/src/$utility" "$output/$utility-gcc"
      cp "$clang_build/src/$utility" "$output/$utility-clang"
      readelf -d "$output/$utility-gcc" > "$output/$utility-gcc.dynamic"
      readelf -d "$output/$utility-clang" > "$output/$utility-clang.dynamic"
    done
    python3 /work/tests/diffutils-oracle-differential.py \
      --gcc-cmp "$output/cmp-gcc" --clang-cmp "$output/cmp-clang" \
      --gcc-diff "$output/diff-gcc" --clang-diff "$output/diff-clang" \
      --gcc-diff3 "$output/diff3-gcc" --clang-diff3 "$output/diff3-clang" \
      --gcc-sdiff "$output/sdiff-gcc" --clang-sdiff "$output/sdiff-clang" \
      --output "$output/differential.json"
  '
