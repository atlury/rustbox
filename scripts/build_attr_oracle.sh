#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-attr:2026-11-21 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    release=/work/work/upstream/attr-2.6.0
    volume=/rustbox-attr
    source=$volume/source
    gcc_build=$volume/canonical-gcc
    clang_build=$volume/canonical-clang
    sanitizer_build=$volume/canonical-sanitizer
    evidence=/work/work/analysis/attr-2.6.0/oracle

    run_logged()
    {
      log=$1
      shift
      if "$@" >"$log" 2>&1; then cat "$log"; else status=$?; cat "$log"; return "$status"; fi
    }

    rm -rf "$source" "$gcc_build" "$clang_build" "$sanitizer_build" "$evidence"
    mkdir -p "$source" "$evidence"
    cp -a "$release/." "$source/"

    build_one()
    {
      compiler=$1
      cc=$2
      build=$3
      mkdir "$build"
      cd "$build"
      CC="$cc" CFLAGS="-O2 -g -fno-omit-frame-pointer" \
        "$source/configure" --disable-dependency-tracking --disable-nls \
          --disable-shared --enable-static
      bear --output compile_commands.json -- make -j"$(nproc)"
      chown -R nobody:nogroup "$build"
      run_logged "$evidence/$compiler-check.log" \
        runuser --user=nobody -- make -j"$(nproc)" check
      cp compile_commands.json "$evidence/$compiler-compile-commands.json"
      cp attr getfattr setfattr "$evidence/"
      mv "$evidence/attr" "$evidence/attr-$compiler"
      mv "$evidence/getfattr" "$evidence/getfattr-$compiler"
      mv "$evidence/setfattr" "$evidence/setfattr-$compiler"
    }

    build_one gcc gcc "$gcc_build"
    build_one clang clang-18 "$clang_build"

    mkdir "$sanitizer_build"
    cd "$sanitizer_build"
    CC=gcc CFLAGS="-O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer" \
      LDFLAGS="-fsanitize=address,undefined" \
      "$source/configure" --disable-dependency-tracking --disable-nls \
        --disable-shared --enable-static
    bear --force-wrapper --output compile_commands.json -- make -j"$(nproc)"
    chown -R nobody:nogroup "$sanitizer_build"
    ASAN_OPTIONS=detect_leaks=1:halt_on_error=1 UBSAN_OPTIONS=halt_on_error=1 \
      run_logged "$evidence/sanitizer-check.log" \
        runuser --user=nobody -- make -j"$(nproc)" check
    cp compile_commands.json "$evidence/sanitizer-compile-commands.json"

    python3 /work/tests/attr-oracle-differential.py \
      --gcc-directory "$evidence" --clang-directory "$evidence" \
      --output "$evidence/differential.json"

    cd "$volume"
    : > valgrind-target
    valgrind --leak-check=full --show-leak-kinds=all \
      --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
      --log-file="$evidence/valgrind-setfattr.log" \
      "$evidence/setfattr-gcc" -n user.rustbox -v canonical valgrind-target
    valgrind --leak-check=full --show-leak-kinds=all \
      --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
      --log-file="$evidence/valgrind-getfattr.log" \
      "$evidence/getfattr-gcc" -n user.rustbox valgrind-target \
      > "$evidence/valgrind-getfattr.out"
    for utility in setfattr getfattr; do
      grep -q "ERROR SUMMARY: 0 errors" "$evidence/valgrind-$utility.log"
      grep -q "definitely lost: 0 bytes in 0 blocks" "$evidence/valgrind-$utility.log"
      grep -q "indirectly lost: 0 bytes in 0 blocks" "$evidence/valgrind-$utility.log"
      grep -q "possibly lost: 0 bytes in 0 blocks" "$evidence/valgrind-$utility.log"
    done
  '
