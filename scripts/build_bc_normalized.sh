#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
"$root/scripts/normalize_bc.sh"
RUSTBOX_TOOL_IMAGE=rustbox-bc:2026-11-21 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    volume=/rustbox-bc
    source=$volume/normalized-source
    output=/work/work/analysis/bc-1.08.2/normalized
    oracle=/work/work/analysis/bc-1.08.2/oracle
    gcc_build=$volume/normalized-gcc
    clang_build=$volume/normalized-clang
    sanitizer_build=$volume/normalized-sanitizer

    run_logged()
    {
      log=$1
      shift
      if "$@" >"$log" 2>&1; then cat "$log"; else status=$?; cat "$log"; return "$status"; fi
    }

    rm -rf "$gcc_build" "$clang_build" "$sanitizer_build"
    mkdir -p "$gcc_build" "$clang_build" "$sanitizer_build" "$output"

    build_one()
    {
      compiler=$1
      build=$2
      cc=$3
      cd "$build"
      CC="$cc" CFLAGS="-O2 -g -fno-omit-frame-pointer" \
        "$source/configure" --disable-dependency-tracking \
          --without-readline --without-libedit
      bear --output compile_commands.json -- make -j"$(nproc)"
      run_logged "$output/$compiler-check.log" make -j"$(nproc)" check
      : >"$output/$compiler-upstream-tests.log"
      for test_file in "$source"/Test/*.b "$source"/Test/*.bc; do
        test_name=$(basename "$test_file")
        case $test_name in checklib.b) test_timeout=1800 ;; *) test_timeout=600 ;; esac
        timeout "$test_timeout" "$build/bc/bc" -q -l "$test_file" </dev/null \
          >"$output/$compiler-$test_name.out" 2>"$output/$compiler-$test_name.err"
        cmp "$output/$compiler-$test_name.out" "$oracle/$compiler-$test_name.out"
        cmp "$output/$compiler-$test_name.err" "$oracle/$compiler-$test_name.err"
        printf "%s pass\n" "$test_name" >>"$output/$compiler-upstream-tests.log"
      done
    }

    build_one gcc "$gcc_build" gcc
    build_one clang "$clang_build" clang-18

    cd "$sanitizer_build"
    CC=gcc CFLAGS="-O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer" \
      LDFLAGS="-fsanitize=address,undefined" \
      "$source/configure" --disable-dependency-tracking \
        --without-readline --without-libedit
    bear --force-wrapper --output compile_commands.json -- make -j"$(nproc)"
    run_logged "$output/sanitizer-check.log" env \
      ASAN_OPTIONS=detect_leaks=1:halt_on_error=1 UBSAN_OPTIONS=halt_on_error=1 \
      make -j"$(nproc)" check
    : >"$output/sanitizer-upstream-tests.log"
    for test_file in "$source"/Test/*.b "$source"/Test/*.bc; do
      test_name=$(basename "$test_file")
      test "$test_name" != checklib.b || continue
      timeout 1200 env ASAN_OPTIONS=detect_leaks=1:halt_on_error=1 \
        UBSAN_OPTIONS=halt_on_error=1 \
        "$sanitizer_build/bc/bc" -q -l "$test_file" </dev/null >/dev/null
      printf "%s pass\n" "$test_name" >>"$output/sanitizer-upstream-tests.log"
    done

    cp "$gcc_build/compile_commands.json" "$output/gcc-compile-commands.json"
    cp "$clang_build/compile_commands.json" "$output/clang-compile-commands.json"
    cp "$sanitizer_build/compile_commands.json" "$output/sanitizer-compile-commands.json"
    cp "$gcc_build/config.h" "$output/config-gcc.h"
    cp "$clang_build/config.h" "$output/config-clang.h"
    cp "$gcc_build/bc/bc" "$output/bc-gcc"
    cp "$gcc_build/dc/dc" "$output/dc-gcc"
    cp "$clang_build/bc/bc" "$output/bc-clang"
    cp "$clang_build/dc/dc" "$output/dc-clang"
    cp "$gcc_build/bc/main.o" "$output/bc-main-gcc.o"
    cp "$gcc_build/dc/dc.o" "$output/dc-main-gcc.o"
    cp "$clang_build/bc/main.o" "$output/bc-main-clang.o"
    cp "$clang_build/dc/dc.o" "$output/dc-main-clang.o"

    python3 /work/tests/bc-oracle-differential.py \
      --gcc-bc "$oracle/bc-gcc" --clang-bc "$output/bc-gcc" \
      --gcc-dc "$oracle/dc-gcc" --clang-dc "$output/dc-gcc" \
      --output "$output/canonical-normalized-gcc-differential.json"
    python3 /work/tests/bc-oracle-differential.py \
      --gcc-bc "$oracle/bc-clang" --clang-bc "$output/bc-clang" \
      --gcc-dc "$oracle/dc-clang" --clang-dc "$output/dc-clang" \
      --output "$output/canonical-normalized-clang-differential.json"

    printf "scale=30\n1/7\n" >"$output/valgrind-bc.input"
    valgrind --leak-check=full --show-leak-kinds=all \
      --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
      --log-file="$output/valgrind-bc.log" \
      "$output/bc-gcc" -q <"$output/valgrind-bc.input" >"$output/valgrind-bc.out"
    printf "20 k 1 7 / p\n" >"$output/valgrind-dc.input"
    valgrind --leak-check=full --show-leak-kinds=all \
      --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
      --log-file="$output/valgrind-dc.log" \
      "$output/dc-gcc" <"$output/valgrind-dc.input" >"$output/valgrind-dc.out"
    grep -q "ERROR SUMMARY: 0 errors" "$output/valgrind-bc.log"
    grep -q "ERROR SUMMARY: 0 errors" "$output/valgrind-dc.log"
  '
