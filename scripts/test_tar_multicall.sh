#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
exec "$root/scripts/run_multicall_tool.sh" sh -eu -c '
    output=/work/work/analysis/tar-1.35/multicall
    rustbox=${RUSTBOX_TEST_ELF:-/rustbox-coreutils/canonical-clang-no-security-compdb/src/rustbox}
    canonical=/work/work/analysis/tar-1.35/normalized/clang-root
    dispatch=$output/dispatch-root
    rm -rf "$output"
    mkdir -p "$output" "$dispatch/usr/bin" "$dispatch/usr/libexec"
    ln -s "$rustbox" "$dispatch/usr/bin/tar"
    ln -s "$rustbox" "$dispatch/usr/bin/zstd"
    ln -s "$rustbox" "$dispatch/usr/libexec/rmt"

    PATH="$dispatch/usr/bin:$PATH" python3 /work/tests/tar-oracle-differential.py \
      --gcc-root "$canonical" --clang-root "$dispatch" \
      --output "$output/differential.json"

    scratch=$(mktemp -d /tmp/rustbox-tar-multicall.XXXXXX)
    trap '"'"'rm -rf "$scratch"'"'"' EXIT HUP INT TERM
    mkdir "$scratch/source" "$scratch/extracted"
    printf "multicall tar payload\n" >"$scratch/source/payload"
    dd if=/dev/zero of="$scratch/source/sparse" bs=1 count=0 \
      seek=1048576 2>/dev/null
    ln -s payload "$scratch/source/link"
    valgrind --leak-check=full --show-leak-kinds=all \
      --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
      --log-file="$output/valgrind-create.log" \
      "$rustbox" tar --format=posix -cf "$scratch/archive.tar" \
      -C "$scratch/source" .
    valgrind --leak-check=full --show-leak-kinds=all \
      --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
      --log-file="$output/valgrind-list.log" \
      "$rustbox" tar -tf "$scratch/archive.tar"
    valgrind --leak-check=full --show-leak-kinds=all \
      --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
      --log-file="$output/valgrind-extract.log" \
      "$rustbox" tar -xf "$scratch/archive.tar" -C "$scratch/extracted"
    set +e
    printf "X\n" | valgrind --leak-check=full --show-leak-kinds=all \
      --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
      --log-file="$output/valgrind-rmt.log" "$rustbox" rmt \
      >"$output/rmt-invalid.stdout" 2>"$output/rmt-invalid.stderr"
    rmt_status=$?
    set -e
    test "$rmt_status" -eq 1
    cmp "$scratch/source/payload" "$scratch/extracted/payload"
    cmp "$scratch/source/sparse" "$scratch/extracted/sparse"
    test "$(readlink "$scratch/extracted/link")" = payload
    for operation in create list extract rmt; do
      grep -q "ERROR SUMMARY: 0 errors" "$output/valgrind-$operation.log"
      grep -q "definitely lost: 0 bytes in 0 blocks" "$output/valgrind-$operation.log"
      grep -q "indirectly lost: 0 bytes in 0 blocks" "$output/valgrind-$operation.log"
      grep -q "possibly lost: 0 bytes in 0 blocks" "$output/valgrind-$operation.log"
    done
  '
