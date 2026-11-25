#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
exec "$root/scripts/run_multicall_tool.sh" sh -eu -c '
    output=/work/work/analysis/xz-5.8.4/multicall
    rustbox=${RUSTBOX_TEST_ELF:-/rustbox-coreutils/canonical-clang-no-security-compdb/src/rustbox}
    source=/work/work/analysis/xz-5.8.4/normalized/clang-root/usr/bin
    canonical=/rustbox-xz/multicall-canonical
    dispatch=/rustbox-xz/multicall-dispatch
    names="xz unxz xzcat lzma unlzma lzcat xzdec lzmadec lzmainfo xzdiff xzcmp xzegrep xzfgrep xzgrep xzless xzmore lzdiff lzcmp lzgrep lzegrep lzfgrep lzmore lzless"

    rm -rf "$output" "$canonical" "$dispatch"
    mkdir -p "$output" "$canonical" "$dispatch"
    cp -R "$source/." "$canonical/"
    ln -sf /work/work/analysis/less-710/normalized/clang/less "$canonical/less"
    for name in $names; do
      ln -s "$rustbox" "$dispatch/$name"
    done

    python3 /work/tests/xz-oracle-differential.py \
      --gcc-directory "$canonical" --clang-directory "$dispatch" \
      --output "$output/differential.json"
    (
      cd /work/work/analysis/xz-5.8.4/normalized/c2rust-source/tests
      srcdir=. ./test_scripts.sh "$dispatch"
      echo "test_scripts.sh: PASS"
    ) >"$output/upstream-scripts.log" 2>&1

    printf "alpha beta gamma\nneedle one\n%.0s" $(seq 1 2048) >"$output/input"
    "$canonical/xz" --threads=1 --check=sha256 -c "$output/input" \
      >"$output/canonical.xz"
    valgrind --leak-check=full --show-leak-kinds=all \
      --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
      --log-file="$output/valgrind-compress.log" \
      "$rustbox" xz --threads=1 --check=sha256 -c "$output/input" \
      >"$output/multicall.xz"
    valgrind --leak-check=full --show-leak-kinds=all \
      --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
      --log-file="$output/valgrind-decompress.log" \
      "$rustbox" xz --decompress --stdout "$output/canonical.xz" \
      >"$output/multicall.out"
    for operation in compress decompress; do
      grep -q "ERROR SUMMARY: 0 errors" "$output/valgrind-$operation.log"
      grep -q "definitely lost: 0 bytes in 0 blocks" "$output/valgrind-$operation.log"
      grep -q "indirectly lost: 0 bytes in 0 blocks" "$output/valgrind-$operation.log"
      grep -q "possibly lost: 0 bytes in 0 blocks" "$output/valgrind-$operation.log"
      sed -n "/HEAP SUMMARY/,+6p" "$output/valgrind-$operation.log" \
        | sed "s/^==[0-9]*== *//" >"$output/valgrind-$operation-heap"
    done
    cmp "$output/canonical.xz" "$output/multicall.xz"
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
