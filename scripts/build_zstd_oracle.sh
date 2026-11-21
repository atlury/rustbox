#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-zstd:2026-11-22 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    release=/work/work/upstream/zstd-1.5.7
    volume=/rustbox-zstd
    evidence=/work/work/analysis/zstd-1.5.7/oracle
    feature_flags="HAVE_ZLIB=0 HAVE_LZMA=0 HAVE_LZ4=0 BACKTRACE=0"
    rm -rf "$volume/source-gcc" "$volume/source-clang" \
      "$volume/source-sanitizer" "$evidence"
    mkdir -p "$evidence"

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
      source=$volume/source-$compiler
      cp -a "$release" "$source"
      cd "$source"
      bear --output compile_commands.json -- \
        make -j"$(nproc)" zstd-release CC="$cc" CFLAGS="$flags" \
          LDFLAGS="$linker_flags" $feature_flags
      run_logged "$evidence/$compiler-check.log" \
        make -j"$(nproc)" check CC="$cc" CFLAGS="$flags" \
          LDFLAGS="$linker_flags" $feature_flags
      make -C programs install PREFIX=/usr DESTDIR="$evidence/$compiler-root" \
        CC="$cc" CFLAGS="$flags" LDFLAGS="$linker_flags" $feature_flags
      cp compile_commands.json "$evidence/$compiler-compile-commands.json"
    }

    build_one gcc gcc "-O2 -g -fno-omit-frame-pointer" ""
    build_one clang clang-18 "-O2 -g -fno-omit-frame-pointer" ""
    build_one sanitizer gcc \
      "-O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer" \
      "-fsanitize=address,undefined"

    python3 /work/tests/zstd-oracle-differential.py \
      --gcc-directory "$evidence/gcc-root/usr/bin" \
      --clang-directory "$evidence/clang-root/usr/bin" \
      --output "$evidence/differential.json"

    cd "$volume"
    python3 -c "from pathlib import Path; Path(\"valgrind-input\").write_bytes((b\"the quick brown fox\\n\" * 4096) + bytes(range(256)))"
    cp valgrind-input valgrind-expected
    valgrind --leak-check=full --show-leak-kinds=all \
      --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
      --log-file="$evidence/valgrind-compress.log" \
      "$evidence/gcc-root/usr/bin/zstd" -T1 --keep --force valgrind-input
    valgrind --leak-check=full --show-leak-kinds=all \
      --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
      --log-file="$evidence/valgrind-decompress.log" \
      "$evidence/gcc-root/usr/bin/zstd" --decompress --keep --force valgrind-input.zst
    cmp valgrind-expected valgrind-input
    for operation in compress decompress; do
      grep -q "ERROR SUMMARY: 0 errors" "$evidence/valgrind-$operation.log"
      grep -q "definitely lost: 0 bytes in 0 blocks" "$evidence/valgrind-$operation.log"
      grep -q "indirectly lost: 0 bytes in 0 blocks" "$evidence/valgrind-$operation.log"
      grep -q "possibly lost: 0 bytes in 0 blocks" "$evidence/valgrind-$operation.log"
    done
  '
