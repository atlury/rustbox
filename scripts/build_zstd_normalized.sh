#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
"$root/scripts/normalize_zstd.sh"
RUSTBOX_TOOL_IMAGE=rustbox-zstd:2026-11-22 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    volume=/rustbox-zstd
    normalized=$volume/normalized-source
    output=/work/work/analysis/zstd-1.5.7/normalized
    oracle=/work/work/analysis/zstd-1.5.7/oracle
    feature_flags="HAVE_ZLIB=0 HAVE_LZMA=0 HAVE_LZ4=0 BACKTRACE=0 ZSTD_NO_ASM=1"

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
      flags=$3
      linker_flags=$4
      source=$volume/normalized-$compiler
      rm -rf "$source" "$output/$compiler-root"
      cp -a "$normalized" "$source"
      cd "$source"
      bear --output compile_commands.json -- \
        make -j"$(nproc)" zstd-release CC="$cc" CFLAGS="$flags" \
          LDFLAGS="$linker_flags" $feature_flags
      run_logged "$output/$compiler-check.log" \
        make -j"$(nproc)" check CC="$cc" CFLAGS="$flags" \
          LDFLAGS="$linker_flags" $feature_flags
      make -C programs install PREFIX=/usr DESTDIR="$output/$compiler-root" \
        CC="$cc" CFLAGS="$flags" LDFLAGS="$linker_flags" $feature_flags
      cp compile_commands.json "$output/$compiler-compile-commands.json"
    }

    mkdir -p "$output"
    build_one gcc gcc "-O2 -g -fno-omit-frame-pointer" ""
    build_one clang clang-18 "-O2 -g -fno-omit-frame-pointer" ""
    build_one sanitizer gcc \
      "-O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer" \
      "-fsanitize=address,undefined"

    python3 /work/tests/zstd-oracle-differential.py \
      --gcc-directory "$oracle/gcc-root/usr/bin" \
      --clang-directory "$output/gcc-root/usr/bin" \
      --output "$output/canonical-normalized-gcc-differential.json"
    python3 /work/tests/zstd-oracle-differential.py \
      --gcc-directory "$oracle/clang-root/usr/bin" \
      --clang-directory "$output/clang-root/usr/bin" \
      --output "$output/canonical-normalized-clang-differential.json"
  '
