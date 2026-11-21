#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-grep:2026-11-21 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    release=/work/work/upstream/grep-3.12
    volume=/rustbox-grep
    source=$volume/source
    output=/work/work/analysis/grep-3.12/oracle
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
    # mb-non-UTF8-perf-Fw intentionally processes ten million records under
    # fixed 30/500-second wall-clock limits.  ASan changes that performance
    # contract without adding a functional check, so run every other Grep
    # case plus the complete gnulib suite under instrumentation.
    sanitizer_tests=$(make -s -C tests --no-print-directory \
      --eval="print-tests: ; @echo \$(TESTS)" print-tests)
    sanitizer_tests=$(printf "%s\n" "$sanitizer_tests" | tr " " "\n" \
      | grep -v "^mb-non-UTF8-perf-Fw$" | tr "\n" " ")
    {
      runuser --user=nobody -- env \
        ASAN_OPTIONS=detect_leaks=0:halt_on_error=1:allocator_may_return_null=1 \
        UBSAN_OPTIONS=halt_on_error=1 \
        make -C tests -j"$(nproc)" check TESTS="$sanitizer_tests"
      # Gnulib test-strstr has a fixed SIGALRM performance deadline.  ASan
      # allocator overhead plus a fully parallel suite can consume that budget;
      # serialize this instrumented suite while retaining every test.
      runuser --user=nobody -- env \
        ASAN_OPTIONS=detect_leaks=0:halt_on_error=1:allocator_may_return_null=1 \
        UBSAN_OPTIONS=halt_on_error=1 \
        make -C gnulib-tests -j1 check
    } >"$output/sanitizer-check.log" 2>&1 || {
      status=$?
      cat "$output/sanitizer-check.log"
      exit "$status"
    }
    cat "$output/sanitizer-check.log"

    printf "alpha\nbeta\ngamma\n" > "$output/input"
    for compiler in gcc clang; do
      case $compiler in
        gcc) binary=$gcc_build/src/grep ;;
        clang) binary=$clang_build/src/grep ;;
      esac
      "$binary" -n -E "alpha|gamma" "$output/input" > "$output/smoke-$compiler.out"
    done
    cmp "$output/smoke-gcc.out" "$output/smoke-clang.out"

    valgrind --leak-check=full --show-leak-kinds=all \
      --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
      --log-file="$output/valgrind.log" \
      "$gcc_build/src/grep" -n -E "alpha|gamma" "$output/input" \
      > "$output/valgrind.out" || valgrind_status=$?
    test "${valgrind_status:-0}" -eq 99
    grep -q "ERROR SUMMARY: 3 errors" "$output/valgrind.log"
    grep -q "definitely lost: 0 bytes in 0 blocks" "$output/valgrind.log"
    grep -q "indirectly lost: 0 bytes in 0 blocks" "$output/valgrind.log"
    grep -q "possibly lost: 18,688 bytes in 11 blocks" "$output/valgrind.log"
    grep -q "still reachable: 119,466 bytes in 39 blocks" "$output/valgrind.log"

    cp "$gcc_build/compile_commands.json" "$output/gcc-compile-commands.json"
    cp "$clang_build/compile_commands.json" "$output/clang-compile-commands.json"
    cp "$sanitizer_build/compile_commands.json" "$output/sanitizer-compile-commands.json"
    cp "$gcc_build/config.h" "$output/config-gcc.h"
    cp "$clang_build/config.h" "$output/config-clang.h"
    cmp "$gcc_build/lib/colorize.c" "$clang_build/lib/colorize.c"
    cp "$gcc_build/lib/colorize.c" "$output/colorize.c"
    cp "$gcc_build/src/grep" "$output/grep-gcc"
    cp "$clang_build/src/grep" "$output/grep-clang"
    cp "$gcc_build/src/egrep" "$output/egrep-gcc"
    cp "$gcc_build/src/fgrep" "$output/fgrep-gcc"
    cp "$clang_build/src/egrep" "$output/egrep-clang"
    cp "$clang_build/src/fgrep" "$output/fgrep-clang"
    readelf -d "$output/grep-gcc" > "$output/grep-gcc.dynamic"
    readelf -d "$output/grep-clang" > "$output/grep-clang.dynamic"
    python3 /work/tests/grep-oracle-differential.py \
      --gcc "$output/grep-gcc" --clang "$output/grep-clang" \
      --output "$output/differential.json"
  '
