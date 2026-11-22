#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
"$root/scripts/normalize_tar.sh"
RUSTBOX_TOOL_IMAGE=rustbox-tar:2026-11-22 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    volume=/rustbox-tar
    release=$volume/normalized-source
    output=/work/work/analysis/tar-1.35/normalized
    oracle=/work/work/analysis/tar-1.35/oracle
    configure_flags="--without-selinux --without-libiconv-prefix"
    normalization_manifest=$output/normalization.json
    mkdir -p "$output"

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
      source=$volume/normalized-$compiler
      normalized_tree=$(python3 -c \
        "import json,sys; print(json.load(open(sys.argv[1]))[\"normalized_tree_sha256\"])" \
        "$normalization_manifest")
      expected_stamp=$(printf "%s\n" \
        "$normalized_tree|$compiler|$cc|$flags|$linker_flags|$configure_flags" \
        | sha256sum | cut -d " " -f 1)
      actual_stamp=$(cat "$source/.rustbox-normalization-stamp" 2>/dev/null || true)
      if test ! -f "$source/compile_commands.json" \
          || test "$actual_stamp" != "$expected_stamp"; then
        rm -f "$output/$compiler-check.log" \
          "$output/$compiler-compile-commands.json"
        rm -rf "$output/$compiler-root"
        rm -rf "$source"
        cp -a "$release" "$source"
        cd "$source"
        FORCE_UNSAFE_CONFIGURE=1 CC="$cc" CFLAGS="$flags" LDFLAGS="$linker_flags" \
          ./configure --prefix=/usr $configure_flags
        bear --output compile_commands.json -- make -j"$(nproc)"
        printf "%s\n" "$expected_stamp" > .rustbox-normalization-stamp
      else
        cd "$source"
      fi
      if ! validate_suite "$output/$compiler-check.log" 2>/dev/null; then
        rm -rf tests/testsuite.dir
        rm -f tests/testsuite.log tests/test-suite.log
        if test "$compiler" = sanitizer; then
          if ASAN_OPTIONS=detect_leaks=0:halt_on_error=1 \
              UBSAN_OPTIONS=halt_on_error=1 \
              make -j"$(nproc)" check >"$output/$compiler-check.log" 2>&1
          then suite_status=0; else suite_status=$?; fi
        else
          if make -j"$(nproc)" check >"$output/$compiler-check.log" 2>&1
          then suite_status=0; else suite_status=$?; fi
        fi
        if test "$suite_status" -eq 0; then
          :
        else
          validate_suite "$output/$compiler-check.log" || {
            cat "$output/$compiler-check.log"
            return "$suite_status"
          }
        fi
      fi
      validate_suite "$output/$compiler-check.log"
      make install DESTDIR="$output/$compiler-root"
      cp compile_commands.json "$output/$compiler-compile-commands.json"
    }

    build_one gcc gcc "-O2 -g -fno-omit-frame-pointer" "" &
    gcc_pid=$!
    build_one clang clang-18 "-O2 -g -fno-omit-frame-pointer" "" &
    clang_pid=$!
    build_one sanitizer gcc \
      "-O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer" \
      "-fsanitize=address,undefined" &
    sanitizer_pid=$!

    build_status=0
    for build_pid in "$gcc_pid" "$clang_pid" "$sanitizer_pid"; do
      wait "$build_pid" || build_status=$?
    done
    test "$build_status" -eq 0

    python3 /work/tests/tar-oracle-differential.py \
      --gcc-root "$oracle/gcc-root" \
      --clang-root "$output/gcc-root" \
      --output "$output/canonical-normalized-gcc-differential.json"
    python3 /work/tests/tar-oracle-differential.py \
      --gcc-root "$oracle/clang-root" \
      --clang-root "$output/clang-root" \
      --output "$output/canonical-normalized-clang-differential.json"
  '
