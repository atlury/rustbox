#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-gzip:2026-11-21 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    release=/work/work/upstream/gzip-1.14
    volume=/rustbox-gzip
    source=$volume/source
    output=/work/work/analysis/gzip-1.14/oracle
    rm -rf "$source" "$volume/oracle-gcc" "$volume/oracle-clang" \
      "$volume/oracle-sanitizer" "$volume/install-gcc" "$volume/install-clang" \
      "$output"
    mkdir -p "$source" "$output"
    cp -a "$release/." "$source/"

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
      build=$volume/oracle-$name
      install=$volume/install-$name
      mkdir -p "$build"
      cd "$build"
      CC="$cc" CFLAGS="-O2 -g -fno-omit-frame-pointer" \
        "$source/configure" --disable-dependency-tracking --prefix=/usr
      bear --output compile_commands.json -- make -j"$(nproc)"
      run_logged "$output/$name-check.log" make -j"$(nproc)" check
      make install DESTDIR="$install"
      cp compile_commands.json "$output/$name-compile-commands.json"
      cp lib/config.h "$output/config-$name.h"
      readelf -d gzip >"$output/gzip-$name.dynamic"
      cp gzip "$output/gzip-$name"
    }

    build_one gcc gcc
    build_one clang clang-18

    build=$volume/oracle-sanitizer
    mkdir -p "$build"
    cd "$build"
    CC=gcc CFLAGS="-O1 -g -fsanitize=address,undefined -fno-sanitize=nonnull-attribute -fno-omit-frame-pointer" \
      LDFLAGS="-fsanitize=address,undefined" \
      "$source/configure" --disable-dependency-tracking --prefix=/usr
    bear --force-wrapper --output compile_commands.json -- make -j"$(nproc)"
    run_logged "$output/sanitizer-check.log" env \
      ASAN_OPTIONS=detect_leaks=0:halt_on_error=1:allocator_may_return_null=1 \
      UBSAN_OPTIONS=halt_on_error=1 make -j"$(nproc)" check
    cp compile_commands.json "$output/sanitizer-compile-commands.json"

    for compiler in gcc clang; do
      install=$volume/install-$compiler/usr/bin
      test "$(find "$install" -maxdepth 1 -type f -printf "%f\n" | sort -u | wc -l)" -eq 14
      for command in gzip gunzip zcat uncompress gzexe zcmp zdiff zegrep zfgrep \
        zforce zgrep zless zmore znew; do
        test -x "$install/$command"
      done
    done
    python3 /work/tests/gzip-oracle-differential.py \
      --gcc-directory "$volume/install-gcc/usr/bin" \
      --clang-directory "$volume/install-clang/usr/bin" \
      --output "$output/differential.json"

    printf "alpha beta gamma\n%.0s" $(seq 1 2048) >"$output/input"
    for compiler in gcc clang; do
      bin=$output/gzip-$compiler
      "$bin" -n -9 -c "$output/input" >"$output/input-$compiler.gz"
      "$bin" -dc "$output/input-$compiler.gz" >"$output/output-$compiler"
      cmp "$output/input" "$output/output-$compiler"
    done
    cmp "$output/input-gcc.gz" "$output/input-clang.gz"

    valgrind --leak-check=full --show-leak-kinds=all \
      --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
      --log-file="$output/valgrind-compress.log" \
      "$output/gzip-gcc" -n -9 -c "$output/input" >"$output/valgrind.gz"
    valgrind --leak-check=full --show-leak-kinds=all \
      --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
      --log-file="$output/valgrind-decompress.log" \
      "$output/gzip-gcc" -dc "$output/valgrind.gz" >"$output/valgrind.out"
    cmp "$output/input" "$output/valgrind.out"
    for operation in compress decompress; do
      grep -q "ERROR SUMMARY: 0 errors" "$output/valgrind-$operation.log"
      grep -q "All heap blocks were freed -- no leaks are possible" \
        "$output/valgrind-$operation.log"
    done
  '
