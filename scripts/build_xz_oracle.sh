#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-xz:2026-11-22 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    release=/work/work/upstream/xz-5.8.4
    volume=/rustbox-xz
    evidence=/work/work/analysis/xz-5.8.4/oracle
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
      cflags=$3
      ldflags=$4
      configure_flags=$5
      source=$volume/source-$compiler
      cp -a "$release" "$source"
      cd "$source"
      ./configure --prefix=/usr --disable-shared --enable-static --disable-nls \
        $configure_flags \
        CC="$cc" CFLAGS="$cflags" LDFLAGS="$ldflags"
      bear --output compile_commands.json -- make -j"$(nproc)" V=1
      run_logged "$evidence/$compiler-check.log" make -j"$(nproc)" check
      make DESTDIR="$evidence/$compiler-root" install
      cp compile_commands.json "$evidence/$compiler-compile-commands.json"
    }

    build_one gcc gcc "-O2 -g -fno-omit-frame-pointer" "" ""
    build_one clang clang-18 "-O2 -g -fno-omit-frame-pointer" "" ""
    build_one sanitizer gcc \
      "-O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer" \
      "-fsanitize=address,undefined" "--disable-sandbox"

    python3 /work/tests/xz-oracle-differential.py \
      --gcc-directory "$evidence/gcc-root/usr/bin" \
      --clang-directory "$evidence/clang-root/usr/bin" \
      --output "$evidence/differential.json"

    cd "$volume"
    python3 -c "from pathlib import Path; Path(\"valgrind-input\").write_bytes((b\"the quick brown fox\\n\" * 4096) + bytes(range(256)))"
    cp valgrind-input valgrind-expected
    valgrind --leak-check=full --show-leak-kinds=all \
      --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
      --log-file="$evidence/valgrind-compress.log" \
      "$evidence/gcc-root/usr/bin/xz" --threads=1 --keep --force valgrind-input
    valgrind --leak-check=full --show-leak-kinds=all \
      --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
      --log-file="$evidence/valgrind-decompress.log" \
      "$evidence/gcc-root/usr/bin/xz" --decompress --keep --force valgrind-input.xz
    cmp valgrind-expected valgrind-input
    for operation in compress decompress; do
      grep -q "ERROR SUMMARY: 0 errors" "$evidence/valgrind-$operation.log"
      grep -q "definitely lost: 0 bytes in 0 blocks" "$evidence/valgrind-$operation.log"
      grep -q "indirectly lost: 0 bytes in 0 blocks" "$evidence/valgrind-$operation.log"
      grep -q "possibly lost: 0 bytes in 0 blocks" "$evidence/valgrind-$operation.log"
    done
  '
