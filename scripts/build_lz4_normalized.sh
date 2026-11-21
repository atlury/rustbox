#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
"$root/scripts/normalize_lz4.sh"
RUSTBOX_TOOL_IMAGE=rustbox-lz4:2026-11-21 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    volume=/rustbox-lz4
    normalized=$volume/normalized-source
    output=/work/work/analysis/lz4-1.11.1/normalized
    oracle=/work/work/analysis/lz4-1.11.1/oracle
    portable="-DLZ4_FORCE_MEMORY_ACCESS=0"

    run_logged()
    {
      log=$1
      shift
      if "$@" >"$log" 2>&1; then cat "$log"; else status=$?; cat "$log"; return "$status"; fi
    }

    build_one()
    {
      compiler=$1
      cc=$2
      source=$volume/normalized-$compiler
      rm -rf "$source"
      cp -a "$normalized" "$source"
      cd "$source"
      bear --output compile_commands.json -- \
        make -j"$(nproc)" V=1 CC="$cc" \
          CFLAGS="-O2 -g -fno-omit-frame-pointer $portable" -C programs all
      run_logged "$output/$compiler-check.log" \
        make -j"$(nproc)" CC="$cc" \
          CFLAGS="-O2 -g -fno-omit-frame-pointer $portable" check
      rm -rf "$output/$compiler"
      mkdir -p "$output/$compiler"
      cp programs/lz4 "$output/$compiler/lz4"
      for alias in lz4c lz4cat unlz4; do
        ln -s lz4 "$output/$compiler/$alias"
      done
      cp compile_commands.json "$output/$compiler-compile-commands.json"
    }

    mkdir -p "$output"
    build_one gcc gcc
    build_one clang clang-18

    sanitizer=$volume/normalized-sanitizer
    rm -rf "$sanitizer"
    cp -a "$normalized" "$sanitizer"
    cd "$sanitizer"
    bear --force-wrapper --output compile_commands.json -- \
      make -j"$(nproc)" V=1 CC=gcc \
        CFLAGS="-O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer $portable" \
        LDFLAGS="-fsanitize=address,undefined" -C programs all
    ASAN_OPTIONS=detect_leaks=1:halt_on_error=1 UBSAN_OPTIONS=halt_on_error=1 \
      run_logged "$output/sanitizer-check.log" \
        make -j"$(nproc)" CC=gcc \
          CFLAGS="-O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer $portable" \
          LDFLAGS="-fsanitize=address,undefined" check
    cp compile_commands.json "$output/sanitizer-compile-commands.json"

    python3 /work/tests/lz4-oracle-differential.py \
      --gcc-directory "$oracle/gcc" --clang-directory "$output/gcc" \
      --output "$output/canonical-normalized-gcc-differential.json"
    python3 /work/tests/lz4-oracle-differential.py \
      --gcc-directory "$oracle/clang" --clang-directory "$output/clang" \
      --output "$output/canonical-normalized-clang-differential.json"

    cd "$volume"
    printf "the quick brown fox\n%.0s" $(seq 1 1024) > normalized-valgrind-input
    valgrind --leak-check=full --show-leak-kinds=all \
      --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
      --log-file="$output/valgrind-compress.log" \
      "$output/gcc/lz4" -f normalized-valgrind-input normalized-valgrind-input.lz4
    valgrind --leak-check=full --show-leak-kinds=all \
      --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
      --log-file="$output/valgrind-decompress.log" \
      "$output/gcc/lz4" -d -f normalized-valgrind-input.lz4 normalized-valgrind-output
    cmp normalized-valgrind-input normalized-valgrind-output
    for operation in compress decompress; do
      grep -q "ERROR SUMMARY: 0 errors" "$output/valgrind-$operation.log"
      grep -q "All heap blocks were freed -- no leaks are possible" \
        "$output/valgrind-$operation.log"
    done
  '
