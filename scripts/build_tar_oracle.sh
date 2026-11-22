#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-tar:2026-11-22 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    release=/work/work/upstream/tar-1.35
    volume=/rustbox-tar
    evidence=/work/work/analysis/tar-1.35/oracle
    configure_flags="--without-selinux --without-libiconv-prefix"
    mkdir -p "$evidence"

    validate_suite()
    {
      log=$1
      failures=$(grep -c " FAILED (" "$log" || true)
      grep -q "224 tests were run" "$log"
      grep -q "20 tests were skipped" "$log"
      if test "$failures" -eq 2; then
        grep -q "222: xattrs: trusted.\* attributes.*FAILED" "$log"
        grep -q "233: capabilities: binary store/restore.*FAILED" "$log"
        grep -q "2 failed unexpectedly" "$log"
      elif test "$failures" -eq 0; then
        grep -Eq "All 224 tests were successful|224 tests were successful" "$log"
      else
        return 1
      fi
    }

    build_one()
    {
      compiler=$1
      cc=$2
      flags=$3
      linker_flags=$4
      source=$volume/source-$compiler
      if test ! -f "$source/compile_commands.json"; then
        rm -rf "$source"
        cp -a "$release" "$source"
        cd "$source"
        FORCE_UNSAFE_CONFIGURE=1 CC="$cc" CFLAGS="$flags" LDFLAGS="$linker_flags" \
          ./configure --prefix=/usr $configure_flags
        bear --output compile_commands.json -- make -j"$(nproc)"
      else
        cd "$source"
      fi
      if ! validate_suite "$evidence/$compiler-check.log" 2>/dev/null; then
        if test "$compiler" = sanitizer; then
          if ASAN_OPTIONS=detect_leaks=0:halt_on_error=1 \
              UBSAN_OPTIONS=halt_on_error=1 \
              make -j"$(nproc)" check >"$evidence/$compiler-check.log" 2>&1
          then suite_status=0; else suite_status=$?; fi
        else
          if make -j"$(nproc)" check >"$evidence/$compiler-check.log" 2>&1
          then suite_status=0; else suite_status=$?; fi
        fi
        if test "$suite_status" -eq 0; then
          :
        else
          validate_suite "$evidence/$compiler-check.log" || {
            cat "$evidence/$compiler-check.log"
            return "$suite_status"
          }
        fi
      fi
      validate_suite "$evidence/$compiler-check.log"
      make install DESTDIR="$evidence/$compiler-root"
      cp compile_commands.json "$evidence/$compiler-compile-commands.json"
    }

    build_one gcc gcc "-O2 -g -fno-omit-frame-pointer" ""
    build_one clang clang-18 "-O2 -g -fno-omit-frame-pointer" ""
    build_one sanitizer gcc \
      "-O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer" \
      "-fsanitize=address,undefined"
  '
