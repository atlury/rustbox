#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
"$root/scripts/normalize_xz.sh"
RUSTBOX_TOOL_IMAGE=rustbox-xz:2026-11-22 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    volume=/rustbox-xz
    normalized=$volume/normalized-source
    output=/work/work/analysis/xz-5.8.4/normalized
    oracle=/work/work/analysis/xz-5.8.4/oracle

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
      cflags=$3
      ldflags=$4
      configure_flags=$5
      source=$volume/normalized-$compiler
      rm -rf "$source" "$output/$compiler-root"
      cp -a "$normalized" "$source"
      cd "$source"
      ./configure --prefix=/usr --disable-shared --enable-static --disable-nls \
        --disable-clmul-crc $configure_flags \
        CC="$cc" CFLAGS="$cflags" LDFLAGS="$ldflags"
      bear --output compile_commands.json -- make -j"$(nproc)" V=1
      run_logged "$output/$compiler-check.log" make -j"$(nproc)" check
      make DESTDIR="$output/$compiler-root" install
      cp compile_commands.json "$output/$compiler-compile-commands.json"
    }

    mkdir -p "$output"
    build_one gcc gcc "-O2 -g -fno-omit-frame-pointer" "" ""
    build_one clang clang-18 "-O2 -g -fno-omit-frame-pointer" "" ""
    build_one sanitizer gcc \
      "-O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer" \
      "-fsanitize=address,undefined" "--disable-sandbox"

    python3 /work/tests/xz-oracle-differential.py \
      --gcc-directory "$oracle/gcc-root/usr/bin" \
      --clang-directory "$output/gcc-root/usr/bin" \
      --output "$output/canonical-normalized-gcc-differential.json"
    python3 /work/tests/xz-oracle-differential.py \
      --gcc-directory "$oracle/clang-root/usr/bin" \
      --clang-directory "$output/clang-root/usr/bin" \
      --output "$output/canonical-normalized-clang-differential.json"
  '
