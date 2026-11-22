#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-findutils:2026-11-22 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    release=/work/work/upstream/findutils-4.10.0
    volume=/rustbox-findutils
    source=$volume/source
    output=/work/work/analysis/findutils-4.10.0/oracle
    configure_flags="--prefix=/usr --localstatedir=/var/lib --without-selinux --disable-dependency-tracking"
    mkdir -p "$source" "$output"
    if test ! -f "$source/configure"; then
      cp -a "$release/." "$source/"
    fi

    build_one()
    {
      compiler=$1
      cc=$2
      flags=$3
      linker_flags=$4
      build=$volume/oracle-$compiler
      root=$output/$compiler-root
      if test ! -x "$build/find/find"; then
        mkdir -p "$build" "$root"
        cd "$build"
        CC="$cc" CFLAGS="$flags" LDFLAGS="$linker_flags" \
          "$source/configure" $configure_flags \
          >"$output/$compiler-configure.log" 2>&1
        bear_mode=--force-preload
        test "$compiler" != sanitizer || bear_mode=--force-wrapper
        bear "$bear_mode" --output compile_commands.json -- \
          make -j"$(nproc)" >"$output/$compiler-build.log" 2>&1
        chmod -R a+rwX "$build"
      else
        cd "$build"
      fi
      if test ! -f .rustbox-oracle-check-complete; then
        if test "$compiler" = sanitizer; then
          set +e
          runuser --user=nobody -- env \
            ASAN_OPTIONS=detect_leaks=0:halt_on_error=1:allocator_may_return_null=1 \
            UBSAN_OPTIONS=halt_on_error=1 \
            make -k -j"$(nproc)" check >"$output/$compiler-check.log" 2>&1
          check_status=$?
          set -e
          test "$check_status" -ne 0
          test "$(grep -c "^FAIL: bigprefix1-1$" "$output/$compiler-check.log")" -eq 1
          test "$(grep -c "^FAIL:" "$output/$compiler-check.log")" -eq 1
        else
          runuser --user=nobody -- make -j"$(nproc)" check \
            >"$output/$compiler-check.log" 2>&1
        fi
        touch .rustbox-oracle-check-complete
      fi
      make install DESTDIR="$root" >"$output/$compiler-install.log" 2>&1
      cp compile_commands.json "$output/$compiler-compile-commands.json"
      find "$root/usr" -type f -o -type l | sort \
        >"$output/$compiler-installed-files.txt"
    }

    build_one gcc gcc "-O2 -g -fno-omit-frame-pointer" ""
    build_one clang clang-18 "-O2 -g -fno-omit-frame-pointer" ""
    build_one sanitizer gcc \
      "-O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer" \
      "-fsanitize=address,undefined"

    python3 - "$output/sanitizer-known-ub.input" <<"PY"
from pathlib import Path
import sys
p = "_" * 200
Path(sys.argv[1]).write_text(
    f"{p}abcd\n{p}abcx\n{p}abcd\nabcd\n{p}abcdF\n{p}abcF\n"
)
PY
    "$volume/oracle-sanitizer/locate/frcode" \
      <"$output/sanitizer-known-ub.input" \
      >"$output/sanitizer-known-ub.db"
    set +e
    UBSAN_OPTIONS=halt_on_error=1 \
      "$volume/oracle-sanitizer/locate/locate" \
      -d "$output/sanitizer-known-ub.db" -r . \
      >"$output/sanitizer-known-ub.out" \
      2>"$output/sanitizer-known-ub.log"
    known_status=$?
    set -e
    test "$known_status" -eq 1
    test ! -s "$output/sanitizer-known-ub.out"
    test "$(grep -c "locate.c:200:32: runtime error: left shift of negative value -1" \
      "$output/sanitizer-known-ub.log")" -eq 1

    python3 /work/tests/findutils-oracle-differential.py \
      --gcc-build "$volume/oracle-gcc" \
      --clang-build "$volume/oracle-clang" \
      --output "$output/differential.json"

    for item in find/find xargs/xargs locate/locate; do
      name=$(basename "$item")
      valgrind --leak-check=full --show-leak-kinds=all \
        --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
        --log-file="$output/valgrind-$name.log" \
        "$volume/oracle-gcc/$item" --version \
        >"$output/valgrind-$name.out" 2>&1
      grep -q "ERROR SUMMARY: 0 errors" "$output/valgrind-$name.log"
      grep -Eq "All heap blocks were freed|definitely lost: 0 bytes" \
        "$output/valgrind-$name.log"
      grep -Eq "All heap blocks were freed|indirectly lost: 0 bytes" \
        "$output/valgrind-$name.log"
      grep -Eq "All heap blocks were freed|possibly lost: 0 bytes" \
        "$output/valgrind-$name.log"
    done
    printf "" | valgrind --leak-check=full --show-leak-kinds=all \
      --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
      --log-file="$output/valgrind-frcode.log" \
      "$volume/oracle-gcc/locate/frcode" \
      >"$output/valgrind-frcode.out" 2>&1
    grep -q "ERROR SUMMARY: 0 errors" "$output/valgrind-frcode.log"
    grep -Eq "All heap blocks were freed|definitely lost: 0 bytes" \
      "$output/valgrind-frcode.log"
    grep -Eq "All heap blocks were freed|indirectly lost: 0 bytes" \
      "$output/valgrind-frcode.log"
    grep -Eq "All heap blocks were freed|possibly lost: 0 bytes" \
      "$output/valgrind-frcode.log"
  '
