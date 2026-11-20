#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
"$root/scripts/normalize_patch.sh"
RUSTBOX_TOOL_IMAGE=rustbox-patch:2026-11-20 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    readonly volume=/rustbox-patch
    readonly source=$volume/normalized-source
    readonly gcc_build=$volume/normalized-gcc
    readonly clang_build=$volume/normalized-clang
    readonly sanitizer_build=$volume/normalized-sanitizer
    readonly output=/work/work/analysis/patch-2.8/normalized

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

    rm -rf "$gcc_build" "$clang_build" "$sanitizer_build"
    mkdir -p "$gcc_build" "$clang_build" "$sanitizer_build" "$output"

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
    CC=gcc CFLAGS="-O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer" \
      LDFLAGS="-fsanitize=address,undefined" \
      "$source/configure" --disable-dependency-tracking
    bear --force-wrapper --output compile_commands.json -- make -j"$(nproc)"
    chown -R nobody:nogroup "$sanitizer_build"
    run_logged "$output/sanitizer-check.log" \
      runuser --user=nobody -- env \
        ASAN_OPTIONS=detect_leaks=1:halt_on_error=1 \
        UBSAN_OPTIONS=halt_on_error=1 \
        make -j"$(nproc)" check

    rm -rf "$output/valgrind-case"
    mkdir "$output/valgrind-case"
    printf "old line\nsecond line\n" > "$output/valgrind-case/input"
    cat > "$output/valgrind-case/change.diff" <<EOF
--- input
+++ input
@@ -1,2 +1,2 @@
-old line
+new line
 second line
EOF
    cd "$output/valgrind-case"
    valgrind --leak-check=full --show-leak-kinds=all \
      --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
      --log-file="$output/valgrind.log" \
      "$gcc_build/src/patch" -i change.diff input > "$output/valgrind.out"
    grep -q "ERROR SUMMARY: 0 errors" "$output/valgrind.log"
    grep -q "definitely lost: 0 bytes in 0 blocks" "$output/valgrind.log"
    grep -q "indirectly lost: 0 bytes in 0 blocks" "$output/valgrind.log"
    grep -q "possibly lost: 0 bytes in 0 blocks" "$output/valgrind.log"

    cp "$gcc_build/compile_commands.json" "$output/gcc-compile-commands.json"
    cp "$clang_build/compile_commands.json" "$output/clang-compile-commands.json"
    cp "$sanitizer_build/compile_commands.json" "$output/sanitizer-compile-commands.json"
    cp "$gcc_build/src/patch" "$output/patch-gcc"
    cp "$clang_build/src/patch" "$output/patch-clang"
    cp "$gcc_build/src/patch.o" "$output/patch-gcc.o"
    cp "$clang_build/src/patch.o" "$output/patch-clang.o"
    cp "$gcc_build/config.h" "$output/config-gcc.h"
    cp "$clang_build/config.h" "$output/config-clang.h"

    python3 /work/tests/patch-oracle-differential.py \
      --gcc /work/work/analysis/patch-2.8/oracle/patch-gcc \
      --clang "$gcc_build/src/patch" \
      --output "$output/canonical-normalized-gcc-differential.json"
    python3 /work/tests/patch-oracle-differential.py \
      --gcc /work/work/analysis/patch-2.8/oracle/patch-clang \
      --clang "$clang_build/src/patch" \
      --output "$output/canonical-normalized-clang-differential.json"
  '
