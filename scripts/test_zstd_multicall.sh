#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
exec "$root/scripts/run_multicall_tool.sh" sh -eu -c '
    output=/work/work/analysis/zstd-1.5.7/multicall
    rustbox=${RUSTBOX_TEST_ELF:-/rustbox-coreutils/canonical-clang-no-security-compdb/src/rustbox}
    source=/rustbox-zstd/normalized-gcc/programs
    canonical=/rustbox-zstd/multicall-canonical
    dispatch=/rustbox-zstd/multicall-dispatch
    names="zstd zstdmt unzstd zstdcat zstdgrep zstdless"

    rm -rf "$output" "$canonical" "$dispatch"
    mkdir -p "$output" "$canonical" "$dispatch"
    ln -s "$source/zstd" "$canonical/zstd"
    for name in zstdmt unzstd zstdcat; do ln -s zstd "$canonical/$name"; done
    cp "$source/zstdgrep" "$source/zstdless" "$canonical/"
    for name in $names; do ln -s "$rustbox" "$dispatch/$name"; done

    python3 /work/tests/zstd-oracle-differential.py \
      --gcc-directory "$canonical" --clang-directory "$dispatch" \
      --output "$output/differential.json"

    python3 -c "from pathlib import Path; Path(\"$output/input\").write_bytes((b\"alpha beta gamma\\nneedle one\\n\" * 2048) + bytes(range(256)))"
    "$canonical/zstd" -T1 --stdout "$output/input" >"$output/canonical.zst"
    valgrind --leak-check=full --show-leak-kinds=all \
      --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
      --log-file="$output/valgrind-compress.log" \
      "$rustbox" zstd -T1 --stdout "$output/input" >"$output/multicall.zst"
    valgrind --leak-check=full --show-leak-kinds=all \
      --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
      --log-file="$output/valgrind-decompress.log" \
      "$rustbox" zstd --decompress --stdout "$output/canonical.zst" \
      >"$output/multicall.out"
    for operation in compress decompress; do
      grep -q "ERROR SUMMARY: 0 errors" "$output/valgrind-$operation.log"
      grep -q "All heap blocks were freed -- no leaks are possible" \
        "$output/valgrind-$operation.log"
      sed -n "/HEAP SUMMARY/,+6p" "$output/valgrind-$operation.log" \
        | sed "s/^==[0-9]*== *//" >"$output/valgrind-$operation-heap"
    done
    cmp "$output/canonical.zst" "$output/multicall.zst"
    cmp "$output/input" "$output/multicall.out"

    cp "$rustbox" "$output/rustbox.unstripped"
    cp "$rustbox" "$output/rustbox.stripped"
    strip --strip-all "$output/rustbox.stripped"
    size -A "$output/rustbox.unstripped" >"$output/rustbox.sections"
    readelf -d "$output/rustbox.unstripped" >"$output/rustbox.dynamic"
    nm -g --defined-only "$output/rustbox.unstripped" >"$output/rustbox.symbols"
    sha256sum "$output/rustbox.unstripped" "$output/rustbox.stripped" \
      >"$output/rustbox.sha256"
  '
