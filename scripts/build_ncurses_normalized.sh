#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-tar:2026-11-22 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    release=/work/work/normalized/ncurses-6.6
    volume=/rustbox-ncurses
    oracle=/work/work/analysis/ncurses-6.6/oracle
    evidence=/work/work/analysis/ncurses-6.6/normalized
    configure_flags="--prefix=/usr --with-shared --with-normal --with-termlib --with-ticlib --without-debug --without-ada --without-cxx-binding --without-tests --enable-pc-files --disable-stripping"
    normalization_sha256=$(sha256sum /work/work/analysis/ncurses-6.6/normalization-manifest.json | cut -d" " -f1)
    rm -rf "$evidence"
    mkdir -p "$evidence"

    build_one()
    {
      compiler=$1
      cc=$2
      flags=$3
      linker_flags=$4
      source=$volume/normalized-$compiler
      root=$evidence/$compiler-root
      configuration="$normalization_sha256|$cc|$flags|$linker_flags|$configure_flags"
      rm -rf "$root"
      if test ! -f "$source/.rustbox-normalized-configuration" ||
          test "$(cat "$source/.rustbox-normalized-configuration")" != "$configuration"; then
        rm -rf "$source"
        cp -a "$release" "$source"
        cd "$source"
        CC="$cc" CFLAGS="$flags" LDFLAGS="$linker_flags" \
          ./configure $configure_flags >"$evidence/$compiler-configure.log" 2>&1
        printf "%s\n" "$configuration" >.rustbox-normalized-configuration
      else
        cd "$source"
        cp config.log "$evidence/$compiler-config.log"
      fi
      if test ! -f .rustbox-normalized-build-complete; then
        make clean >"$evidence/$compiler-clean.log" 2>&1
        make -j"$(nproc)" sources >"$evidence/$compiler-sources.log" 2>&1
        bear_mode=--force-preload
        test "$compiler" != sanitizer || bear_mode=--force-wrapper
        bear "$bear_mode" --output compile_commands.json -- \
          make -j"$(nproc)" >"$evidence/$compiler-build.log" 2>&1
        touch .rustbox-normalized-build-complete
      else
        printf "reused exact immutable normalized build cache\n" \
          >"$evidence/$compiler-build.log"
      fi
      {
        make -C include check
        make -C progs check
      } >"$evidence/$compiler-check.log" 2>&1
      if test "$compiler" = sanitizer; then
        ASAN_OPTIONS=detect_leaks=0:halt_on_error=1 \
          UBSAN_OPTIONS=halt_on_error=1 \
          make install.progs install.libs install.data DESTDIR="$root" \
            >"$evidence/$compiler-install.log" 2>&1
        ! grep -q "runtime error:" "$evidence/$compiler-install.log"
        ! grep -q "ERROR: AddressSanitizer" "$evidence/$compiler-install.log"
      else
        make install.progs install.libs install.data DESTDIR="$root" \
          >"$evidence/$compiler-install.log" 2>&1
      fi
      cp compile_commands.json "$evidence/$compiler-compile-commands.json"
      find "$root/usr" -type f -o -type l | sort >"$evidence/$compiler-installed-files.txt"
    }

    build_one gcc gcc "-O2 -g -fno-omit-frame-pointer" ""
    build_one clang clang-18 "-O2 -g -fno-omit-frame-pointer" ""
    build_one sanitizer gcc \
      "-O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer" \
      "-fsanitize=address,undefined"

    for compiler in gcc clang; do
      diff -qr "$oracle/$compiler-root/usr/share/terminfo" \
        "$evidence/$compiler-root/usr/share/terminfo" \
        >"$evidence/$compiler-terminfo-diff.log"
      python3 /work/tests/ncurses-oracle-differential.py \
        --gcc-root "$oracle/$compiler-root" \
        --clang-root "$evidence/$compiler-root" \
        --output "$evidence/$compiler-differential.json"
    done

    for applet in captoinfo clear infocmp infotocap tabs tic toe tput tset reset; do
      binary=$evidence/gcc-root/usr/bin/$applet
      TERM=xterm TERMINFO="$evidence/gcc-root/usr/share/terminfo" \
        LD_LIBRARY_PATH="$evidence/gcc-root/usr/lib" \
        valgrind --leak-check=full --show-leak-kinds=all \
          --errors-for-leak-kinds=definite,indirect --error-exitcode=99 \
          --log-file="$evidence/valgrind-$applet.log" \
          "$binary" -V >"$evidence/valgrind-$applet.out" 2>&1
      grep -q "ERROR SUMMARY: 0 errors" "$evidence/valgrind-$applet.log"
      grep -Eq "All heap blocks were freed|definitely lost: 0 bytes" \
        "$evidence/valgrind-$applet.log"
      grep -Eq "All heap blocks were freed|indirectly lost: 0 bytes" \
        "$evidence/valgrind-$applet.log"
    done
  '
