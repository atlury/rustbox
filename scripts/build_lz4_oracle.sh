#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-lz4:2026-11-21 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    release=/work/work/upstream/lz4-1.11.1
    volume=/rustbox-lz4
    evidence=/work/work/analysis/lz4-1.11.1/oracle
    rm -rf "$volume/source-gcc" "$volume/source-clang" \
      "$volume/source-sanitizer" "$evidence"
    mkdir -p "$evidence"

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
      source=$volume/source-$compiler
      cp -a "$release" "$source"
      cd "$source"
      bear --output compile_commands.json -- \
        make -j"$(nproc)" V=1 CC="$cc" CFLAGS="-O2 -g -fno-omit-frame-pointer" -C programs all
      run_logged "$evidence/$compiler-check.log" \
        make -j"$(nproc)" CC="$cc" CFLAGS="-O2 -g -fno-omit-frame-pointer" check
      mkdir "$evidence/$compiler"
      cp programs/lz4 "$evidence/$compiler/lz4"
      for alias in lz4c lz4cat unlz4; do
        ln -s lz4 "$evidence/$compiler/$alias"
      done
      cp compile_commands.json "$evidence/$compiler-compile-commands.json"
    }

    build_one gcc gcc
    build_one clang clang-18

    source=$volume/source-sanitizer
    cp -a "$release" "$source"
    cd "$source"
    bear --force-wrapper --output compile_commands.json -- \
      make -j"$(nproc)" V=1 CC=gcc \
        CFLAGS="-O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer" \
        LDFLAGS="-fsanitize=address,undefined" -C programs all
    ASAN_OPTIONS=detect_leaks=1:halt_on_error=1 UBSAN_OPTIONS=halt_on_error=1 \
      run_logged "$evidence/sanitizer-check.log" \
        make -j"$(nproc)" CC=gcc \
          CFLAGS="-O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer" \
          LDFLAGS="-fsanitize=address,undefined" check
    cp compile_commands.json "$evidence/sanitizer-compile-commands.json"

    python3 /work/tests/lz4-oracle-differential.py \
      --gcc-directory "$evidence/gcc" --clang-directory "$evidence/clang" \
      --output "$evidence/differential.json"

    cd "$volume"
    printf "the quick brown fox\n%.0s" $(seq 1 1024) > valgrind-input
    valgrind --leak-check=full --show-leak-kinds=all \
      --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
      --log-file="$evidence/valgrind-compress.log" \
      "$evidence/gcc/lz4" -f valgrind-input valgrind-input.lz4
    valgrind --leak-check=full --show-leak-kinds=all \
      --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
      --log-file="$evidence/valgrind-decompress.log" \
      "$evidence/gcc/lz4" -d -f valgrind-input.lz4 valgrind-output
    cmp valgrind-input valgrind-output
    for operation in compress decompress; do
      grep -q "ERROR SUMMARY: 0 errors" "$evidence/valgrind-$operation.log"
      grep -q "All heap blocks were freed -- no leaks are possible" \
        "$evidence/valgrind-$operation.log"
    done
  '
