#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
"$root/scripts/normalize_gzip.sh"
RUSTBOX_TOOL_IMAGE=rustbox-gzip:2026-11-21 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    volume=/rustbox-gzip
    source=$volume/normalized-source
    output=/work/work/analysis/gzip-1.14/normalized
    oracle=/work/work/analysis/gzip-1.14/oracle
    configure_cache=gl_cv_crc_pclmul=no

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
      install=$volume/normalized-install-$name
      rm -rf "$build" "$install"
      mkdir -p "$build"
      cd "$build"
      env "$configure_cache" CC="$cc" CFLAGS="-O2 -g -fno-omit-frame-pointer" \
        "$source/configure" --disable-dependency-tracking --prefix=/usr
      bear --output compile_commands.json -- make -j"$(nproc)"
      run_logged "$output/$name-check.log" make -j"$(nproc)" check
      make install DESTDIR="$install"
      cp compile_commands.json "$output/$name-compile-commands.json"
      cp lib/config.h "$output/config-$name.h"
      cp gzip "$output/gzip-$name"
    }

    mkdir -p "$output"
    build_one gcc gcc
    build_one clang clang-18

    build=$volume/normalized-sanitizer
    rm -rf "$build"
    mkdir -p "$build"
    cd "$build"
    env "$configure_cache" CC=gcc \
      CFLAGS="-O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer" \
      LDFLAGS="-fsanitize=address,undefined" \
      "$source/configure" --disable-dependency-tracking --prefix=/usr
    bear --force-wrapper --output compile_commands.json -- make -j"$(nproc)"
    run_logged "$output/sanitizer-check.log" env \
      ASAN_OPTIONS=detect_leaks=0:halt_on_error=1:allocator_may_return_null=1 \
      UBSAN_OPTIONS=halt_on_error=1 make -j"$(nproc)" check
    cp compile_commands.json "$output/sanitizer-compile-commands.json"

    python3 /work/tests/gzip-oracle-differential.py \
      --gcc-directory /rustbox-gzip/install-gcc/usr/bin \
      --clang-directory "$volume/normalized-install-gcc/usr/bin" \
      --output "$output/canonical-normalized-gcc-differential.json"
    python3 /work/tests/gzip-oracle-differential.py \
      --gcc-directory /rustbox-gzip/install-clang/usr/bin \
      --clang-directory "$volume/normalized-install-clang/usr/bin" \
      --output "$output/canonical-normalized-clang-differential.json"

    printf "alpha beta gamma\n%.0s" $(seq 1 2048) >"$output/input"
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
