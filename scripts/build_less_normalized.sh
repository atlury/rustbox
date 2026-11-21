#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
"$root/scripts/normalize_less.sh"
RUSTBOX_TOOL_IMAGE=rustbox-less:2026-11-22 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    volume=/rustbox-less
    source=$volume/normalized-source
    output=/work/work/analysis/less-710/normalized
    oracle=/work/work/analysis/less-710/oracle

    run_logged()
    {
      log=$1
      shift
      if "$@" >"$log" 2>&1; then cat "$log"; else status=$?; cat "$log"; return "$status"; fi
    }

    build_one()
    {
      name=$1
      cc=$2
      build=$volume/normalized-$name
      rm -rf "$build"
      mkdir -p "$build" "$output/$name"
      cd "$build"
      CC="$cc" CFLAGS="-O2 -g -fno-omit-frame-pointer" \
        "$source/configure" --prefix=/usr --with-regex=posix
      bear --output compile_commands.json -- make -j"$(nproc)"
      run_logged "$output/$name-check.log" make -j"$(nproc)" check
      cp compile_commands.json "$output/$name-compile-commands.json"
      cp defines.h "$output/defines-$name.h"
      cp less lessecho "$output/$name/"
    }

    mkdir -p "$output"
    build_one gcc gcc
    build_one clang clang-18

    build=$volume/normalized-sanitizer
    rm -rf "$build"
    mkdir -p "$build"
    cd "$build"
    CC=gcc CFLAGS="-O1 -g -fno-omit-frame-pointer" \
      "$source/configure" --prefix=/usr --with-regex=posix
    bear --force-wrapper --output compile_commands.json -- make -j"$(nproc)" SAN=1
    run_logged "$output/sanitizer-check.log" env \
      ASAN_OPTIONS=detect_leaks=0:halt_on_error=1 \
      UBSAN_OPTIONS=halt_on_error=1 make -j"$(nproc)" SAN=1 check
    cp compile_commands.json "$output/sanitizer-compile-commands.json"

    python3 /work/tests/less-oracle-differential.py \
      --gcc-directory "$oracle/gcc" --clang-directory "$output/gcc" \
      --output "$output/canonical-normalized-gcc-differential.json"
    python3 /work/tests/less-oracle-differential.py \
      --gcc-directory "$oracle/clang" --clang-directory "$output/clang" \
      --output "$output/canonical-normalized-clang-differential.json"

    printf "alpha beta gamma\n%.0s" $(seq 1 1024) >"$output/input"
    LESSHISTFILE=- TERM=xterm valgrind --leak-check=full --show-leak-kinds=all \
      --errors-for-leak-kinds=definite,indirect --error-exitcode=99 \
      --log-file="$output/valgrind-less.log" \
      "$output/gcc/less" "$output/input" >"$output/valgrind-less.out"
    cmp "$output/input" "$output/valgrind-less.out"
    valgrind --leak-check=full --show-leak-kinds=all \
      --errors-for-leak-kinds=definite,indirect --error-exitcode=99 \
      --log-file="$output/valgrind-lessecho.log" \
      "$output/gcc/lessecho" -a "alpha beta" >"$output/valgrind-lessecho.out"
    for applet in less lessecho; do
      grep -q "ERROR SUMMARY: 0 errors" "$output/valgrind-$applet.log"
      if grep -q "LEAK SUMMARY" "$output/valgrind-$applet.log"; then
        grep -q "definitely lost: 0 bytes" "$output/valgrind-$applet.log"
        grep -q "indirectly lost: 0 bytes" "$output/valgrind-$applet.log"
      else
        grep -q "All heap blocks were freed -- no leaks are possible" "$output/valgrind-$applet.log"
      fi
    done
  '
