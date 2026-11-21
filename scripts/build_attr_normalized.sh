#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
"$root/scripts/normalize_attr.sh"
RUSTBOX_TOOL_IMAGE=rustbox-attr:2026-11-21 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    volume=/rustbox-attr
    source=$volume/normalized-source
    output=/work/work/analysis/attr-2.6.0/normalized
    oracle=/work/work/analysis/attr-2.6.0/oracle
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
      cc=$2
      build=$3
      cd "$build"
      CC="$cc" CFLAGS="-O2 -g -fno-omit-frame-pointer" \
        "$source/configure" --disable-dependency-tracking --disable-nls \
          --disable-shared --enable-static
      bear --output compile_commands.json -- make -j"$(nproc)"
      chown -R nobody:nogroup "$build"
      run_logged "$output/$compiler-check.log" \
        runuser --user=nobody -- make -j"$(nproc)" check
      cp compile_commands.json "$output/$compiler-compile-commands.json"
      cp attr "$output/attr-$compiler"
      cp getfattr "$output/getfattr-$compiler"
      cp setfattr "$output/setfattr-$compiler"
      cp tools/attr.o "$output/attr-$compiler.o"
      cp tools/getfattr.o "$output/getfattr-$compiler.o"
      cp tools/setfattr.o "$output/setfattr-$compiler.o"
    }

    build_one gcc gcc "$gcc_build"
    build_one clang clang-18 "$clang_build"

    cd "$sanitizer_build"
    CC=gcc CFLAGS="-O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer" \
      LDFLAGS="-fsanitize=address,undefined" \
      "$source/configure" --disable-dependency-tracking --disable-nls \
        --disable-shared --enable-static
    bear --force-wrapper --output compile_commands.json -- make -j"$(nproc)"
    chown -R nobody:nogroup "$sanitizer_build"
    ASAN_OPTIONS=detect_leaks=1:halt_on_error=1 UBSAN_OPTIONS=halt_on_error=1 \
      run_logged "$output/sanitizer-check.log" \
        runuser --user=nobody -- make -j"$(nproc)" check
    cp compile_commands.json "$output/sanitizer-compile-commands.json"

    python3 /work/tests/attr-oracle-differential.py \
      --gcc-directory "$oracle" --gcc-suffix gcc \
      --clang-directory "$output" --clang-suffix gcc \
      --output "$output/canonical-normalized-gcc-differential.json"
    python3 /work/tests/attr-oracle-differential.py \
      --gcc-directory "$oracle" --gcc-suffix clang \
      --clang-directory "$output" --clang-suffix clang \
      --output "$output/canonical-normalized-clang-differential.json"

    cd "$volume"
    : > normalized-valgrind-target
    valgrind --leak-check=full --show-leak-kinds=all \
      --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
      --log-file="$output/valgrind-setfattr.log" \
      "$output/setfattr-gcc" -n user.rustbox -v canonical normalized-valgrind-target
    valgrind --leak-check=full --show-leak-kinds=all \
      --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
      --log-file="$output/valgrind-getfattr.log" \
      "$output/getfattr-gcc" -n user.rustbox normalized-valgrind-target \
      > "$output/valgrind-getfattr.out"
    for utility in setfattr getfattr; do
      grep -q "ERROR SUMMARY: 0 errors" "$output/valgrind-$utility.log"
      grep -q "definitely lost: 0 bytes in 0 blocks" "$output/valgrind-$utility.log"
      grep -q "indirectly lost: 0 bytes in 0 blocks" "$output/valgrind-$utility.log"
      grep -q "possibly lost: 0 bytes in 0 blocks" "$output/valgrind-$utility.log"
    done
  '
