#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-bc:2026-11-21 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    release=/work/work/upstream/bc-1.08.2
    volume=/rustbox-bc
    source=$volume/source
    output=/work/work/analysis/bc-1.08.2/oracle
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
        case $test_name in
          checklib.b) test_timeout=1800 ;;
          *) test_timeout=600 ;;
        esac
        timeout "$test_timeout" "$build/bc/bc" -q -l "$test_file" </dev/null \
          >"$output/$compiler-$test_name.out" \
          2>"$output/$compiler-$test_name.err"
        printf "%s pass\n" "$test_name" >>"$output/$compiler-upstream-tests.log"
      done
    }

    build_one gcc "$gcc_build" gcc
    build_one clang "$clang_build" clang-18

    for path in "$output"/gcc-*.out; do
      name=${path##*/gcc-}
      cmp "$path" "$output/clang-$name"
    done
    for path in "$output"/gcc-*.err; do
      name=${path##*/gcc-}
      cmp "$path" "$output/clang-$name"
    done

    cd "$sanitizer_build"
    CC=gcc CFLAGS="-O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer" \
      LDFLAGS="-fsanitize=address,undefined" \
      "$source/configure" --disable-dependency-tracking \
        --without-readline --without-libedit
    bear --force-wrapper --output compile_commands.json -- make -j"$(nproc)"
    run_logged "$output/sanitizer-check.log" env \
      ASAN_OPTIONS=detect_leaks=1:halt_on_error=1 \
      UBSAN_OPTIONS=halt_on_error=1 \
      make -j"$(nproc)" check
    {
      for test_file in "$source"/Test/*.b "$source"/Test/*.bc; do
        test_name=$(basename "$test_file")
        # checklib.b performs thousands of high-precision transcendental
        # evaluations and takes many minutes even without instrumentation
        # under amd64 emulation.  GCC and Clang run it in full above; the
        # sanitizer gate covers every smaller shipped workload.
        test "$test_name" != checklib.b || continue
        timeout 1200 env ASAN_OPTIONS=detect_leaks=1:halt_on_error=1 \
          UBSAN_OPTIONS=halt_on_error=1 \
          "$sanitizer_build/bc/bc" -q -l "$test_file" </dev/null >/dev/null
        printf "%s pass\n" "$test_name"
      done
    } >"$output/sanitizer-upstream-tests.log" 2>&1

    cp "$gcc_build/bc/bc" "$output/bc-gcc"
    cp "$gcc_build/dc/dc" "$output/dc-gcc"
    cp "$clang_build/bc/bc" "$output/bc-clang"
    cp "$clang_build/dc/dc" "$output/dc-clang"
    cp "$gcc_build/compile_commands.json" "$output/gcc-compile-commands.json"
    cp "$clang_build/compile_commands.json" "$output/clang-compile-commands.json"
    cp "$sanitizer_build/compile_commands.json" "$output/sanitizer-compile-commands.json"
    cp "$gcc_build/config.h" "$output/config-gcc.h"
    cp "$clang_build/config.h" "$output/config-clang.h"
    readelf -d "$output/bc-gcc" >"$output/bc-gcc.dynamic"
    readelf -d "$output/dc-gcc" >"$output/dc-gcc.dynamic"
    readelf -Ws "$output/bc-gcc" >"$output/bc-gcc.symbols"
    readelf -Ws "$output/dc-gcc" >"$output/dc-gcc.symbols"

    python3 /work/tests/bc-oracle-differential.py \
      --gcc-bc "$output/bc-gcc" --clang-bc "$output/bc-clang" \
      --gcc-dc "$output/dc-gcc" --clang-dc "$output/dc-clang" \
      --output "$output/differential.json"

    printf "scale=30\n1/7\n" >"$output/valgrind-bc.input"
    valgrind --leak-check=full --show-leak-kinds=all \
      --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
      --log-file="$output/valgrind-bc.log" \
      "$output/bc-gcc" -q <"$output/valgrind-bc.input" \
      >"$output/valgrind-bc.out"
    printf "20 k 1 7 / p\n" >"$output/valgrind-dc.input"
    valgrind --leak-check=full --show-leak-kinds=all \
      --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
      --log-file="$output/valgrind-dc.log" \
      "$output/dc-gcc" <"$output/valgrind-dc.input" \
      >"$output/valgrind-dc.out"
    grep -q "ERROR SUMMARY: 0 errors" "$output/valgrind-bc.log"
    grep -q "ERROR SUMMARY: 0 errors" "$output/valgrind-dc.log"
  '
