#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
"$root/scripts/normalize_m4.sh"
RUSTBOX_TOOL_IMAGE=rustbox-normalize:2026-11-19 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    readonly volume=/rustbox-m4
    readonly source=$volume/normalized-source
    readonly gcc_build=$volume/normalized-gcc
    readonly clang_build=$volume/normalized-clang
    readonly output=/work/work/analysis/m4-1.4.21/normalized

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

    rm -rf "$gcc_build" "$clang_build"
    mkdir -p "$gcc_build" "$clang_build" "$output"

    cd "$gcc_build"
    CC=gcc CFLAGS="-O2 -g -fno-omit-frame-pointer" \
      "$source/configure" --disable-dependency-tracking
    bear --output compile_commands.json -- make -j"$(nproc)"
    run_logged "$volume/normalized-gcc-check.log" make -j"$(nproc)" check

    cd "$clang_build"
    CC=clang-18 CFLAGS="-O2 -g -fno-omit-frame-pointer" \
      "$source/configure" --disable-dependency-tracking
    bear --output compile_commands.json -- make -j"$(nproc)"
    run_logged "$volume/normalized-clang-check.log" make -j"$(nproc)" check

    printf "define(\`twice\047, \`\$1\$1\047)dnl\ntwice(\`rustbox\047)\n" \
      > "$volume/normalized-valgrind.m4"
    valgrind --leak-check=full --show-leak-kinds=all \
      --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
      --log-file="$volume/normalized-valgrind.log" \
      "$gcc_build/src/m4" "$volume/normalized-valgrind.m4" \
      > "$volume/normalized-valgrind.out"
    test "$(cat "$volume/normalized-valgrind.out")" = rustboxrustbox

    cmp "$volume/canonical-gcc/src/m4" "$gcc_build/src/m4" >/dev/null 2>&1 \
      && { echo "normalized binary unexpectedly equals canonical bytes" >&2; exit 1; } \
      || :
    "$volume/canonical-gcc/src/m4" --version > "$volume/canonical-version.out"
    "$gcc_build/src/m4" --version > "$volume/normalized-version.out"
    cmp "$volume/canonical-version.out" "$volume/normalized-version.out"

    cp "$gcc_build/compile_commands.json" "$output/gcc-compile-commands.json"
    cp "$clang_build/compile_commands.json" "$output/clang-compile-commands.json"
    cp "$gcc_build/tests/test-suite.log" "$output/gcc-test-suite.log"
    cp "$clang_build/tests/test-suite.log" "$output/clang-test-suite.log"
    cp "$volume/normalized-gcc-check.log" "$output/gcc-check.log"
    cp "$volume/normalized-clang-check.log" "$output/clang-check.log"
    cp "$volume/normalized-valgrind.log" "$output/valgrind.log"
    cp "$gcc_build/src/m4" "$output/m4-gcc"
    cp "$clang_build/src/m4" "$output/m4-clang"
  '
