#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
"$root/scripts/normalize_findutils.sh"
RUSTBOX_TOOL_IMAGE=rustbox-findutils:2026-11-22 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    release=/work/work/normalized/findutils-4.10.0
    volume=/rustbox-findutils
    oracle=/work/work/analysis/findutils-4.10.0/oracle
    evidence=/work/work/analysis/findutils-4.10.0/normalized
    configure_flags="--prefix=/usr --localstatedir=/var/lib --without-selinux --disable-dependency-tracking"
    manifest_sha256=$(sha256sum /work/work/analysis/findutils-4.10.0/normalization-manifest.json | cut -d" " -f1)
    mkdir -p "$evidence"

    build_one()
    {
      compiler=$1
      cc=$2
      flags=$3
      linker_flags=$4
      build=$volume/normalized-$compiler
      root=$evidence/$compiler-root
      configuration="$manifest_sha256|$cc|$flags|$linker_flags|$configure_flags"
      check_configuration="$configuration|check-v2"
      if test ! -f "$build/.rustbox-configuration" ||
          test "$(cat "$build/.rustbox-configuration")" != "$configuration"; then
        rm -rf "$build" "$root"
        mkdir -p "$build" "$root"
        cd "$build"
        CC="$cc" CFLAGS="$flags" LDFLAGS="$linker_flags" \
          "$release/configure" $configure_flags \
          >"$evidence/$compiler-configure.log" 2>&1
        bear_mode=--force-preload
        test "$compiler" != sanitizer || bear_mode=--force-wrapper
        bear "$bear_mode" --output compile_commands.json -- \
          make -j"$(nproc)" >"$evidence/$compiler-build.log" 2>&1
        printf "%s\n" "$configuration" >.rustbox-configuration
        chmod -R a+rwX "$build"
      else
        cd "$build"
        rm -rf "$root"
        mkdir -p "$root"
      fi
      if test ! -f "$evidence/$compiler-check.log" ||
          test ! -f "$build/.rustbox-check-configuration" ||
          test "$(cat "$build/.rustbox-check-configuration")" != "$check_configuration"; then
        if test "$compiler" = sanitizer; then
          runuser --user=nobody -- env \
            ASAN_OPTIONS=detect_leaks=0:halt_on_error=1:allocator_may_return_null=1 \
            UBSAN_OPTIONS=halt_on_error=1 \
            TIMEOUT_FACTOR=30 \
            make -j2 check >"$evidence/$compiler-check.log" 2>&1
          ! grep -q "runtime error:" "$evidence/$compiler-check.log"
          ! grep -q "ERROR: AddressSanitizer" "$evidence/$compiler-check.log"
        else
          runuser --user=nobody -- make -j"$(nproc)" check \
            >"$evidence/$compiler-check.log" 2>&1
        fi
        printf "%s\n" "$check_configuration" >"$build/.rustbox-check-configuration"
      fi
      make install DESTDIR="$root" >"$evidence/$compiler-install.log" 2>&1
      cp compile_commands.json "$evidence/$compiler-compile-commands.json"
      find "$root/usr" -type f -o -type l | sort \
        >"$evidence/$compiler-installed-files.txt"
    }

    build_one gcc gcc "-O2 -g -fno-omit-frame-pointer" ""
    build_one clang clang-18 "-O2 -g -fno-omit-frame-pointer" ""
    build_one sanitizer gcc \
      "-O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer" \
      "-fsanitize=address,undefined"

    for compiler in gcc clang; do
      python3 /work/tests/findutils-oracle-differential.py \
        --gcc-build "$volume/oracle-$compiler" \
        --clang-build "$volume/normalized-$compiler" \
        --output "$evidence/$compiler-differential.json"
    done

    for item in find/find xargs/xargs locate/locate locate/frcode; do
      name=$(basename "$item")
      if test "$name" = frcode; then args=""; else args=--version; fi
      valgrind --leak-check=full --show-leak-kinds=all \
        --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
        --log-file="$evidence/valgrind-$name.log" \
        "$volume/normalized-gcc/$item" $args \
        </dev/null >"$evidence/valgrind-$name.out" 2>&1
      grep -q "ERROR SUMMARY: 0 errors" "$evidence/valgrind-$name.log"
      grep -Eq "All heap blocks were freed|definitely lost: 0 bytes" \
        "$evidence/valgrind-$name.log"
      grep -Eq "All heap blocks were freed|indirectly lost: 0 bytes" \
        "$evidence/valgrind-$name.log"
      grep -Eq "All heap blocks were freed|possibly lost: 0 bytes" \
        "$evidence/valgrind-$name.log"
    done
  '
