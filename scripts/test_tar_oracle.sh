#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-tar:2026-11-22 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    evidence=/work/work/analysis/tar-1.35/oracle
    tar_bin=$evidence/gcc-root/usr/bin/tar
    rmt_bin=$evidence/gcc-root/usr/libexec/rmt

    python3 /work/tests/tar-oracle-differential.py \
      --gcc-root "$evidence/gcc-root" \
      --clang-root "$evidence/clang-root" \
      --output "$evidence/differential.json"

    scratch=$(mktemp -d /rustbox-tar/tar-valgrind.XXXXXX)
    trap '"'"'rm -rf "$scratch"'"'"' EXIT HUP INT TERM
    mkdir "$scratch/source" "$scratch/extracted"
    printf "canonical tar payload\n" >"$scratch/source/payload"
    dd if=/dev/zero of="$scratch/source/sparse" bs=1 count=0 seek=1048576 2>/dev/null
    ln -s payload "$scratch/source/link"

    valgrind --leak-check=full --show-leak-kinds=all \
      --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
      --log-file="$evidence/valgrind-create.log" \
      "$tar_bin" --format=posix -cf "$scratch/archive.tar" \
      -C "$scratch/source" .
    valgrind --leak-check=full --show-leak-kinds=all \
      --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
      --log-file="$evidence/valgrind-list.log" \
      "$tar_bin" -tf "$scratch/archive.tar"
    if valgrind --leak-check=full --show-leak-kinds=all \
        --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
        --log-file="$evidence/valgrind-extract.log" \
        "$tar_bin" -xf "$scratch/archive.tar" -C "$scratch/extracted"
    then
      extract_status=0
    else
      extract_status=$?
    fi
    test "$extract_status" -eq 99
    if printf "X\n" | valgrind --leak-check=full --show-leak-kinds=all \
        --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
        --log-file="$evidence/valgrind-rmt.log" "$rmt_bin" \
        >"$evidence/rmt-invalid.stdout" 2>"$evidence/rmt-invalid.stderr"
    then
      rmt_status=0
    else
      rmt_status=$?
    fi
    test "$rmt_status" -eq 1

    cmp "$scratch/source/payload" "$scratch/extracted/payload"
    cmp "$scratch/source/sparse" "$scratch/extracted/sparse"
    test "$(readlink "$scratch/extracted/link")" = payload
    for operation in create list rmt; do
      grep -q "ERROR SUMMARY: 0 errors" "$evidence/valgrind-$operation.log"
      grep -q "definitely lost: 0 bytes in 0 blocks" "$evidence/valgrind-$operation.log"
      grep -q "indirectly lost: 0 bytes in 0 blocks" "$evidence/valgrind-$operation.log"
      grep -q "possibly lost: 0 bytes in 0 blocks" "$evidence/valgrind-$operation.log"
    done
    grep -q "definitely lost: 152 bytes in 2 blocks" "$evidence/valgrind-extract.log"
    grep -q "indirectly lost: 1 bytes in 1 blocks" "$evidence/valgrind-extract.log"
    grep -q "possibly lost: 0 bytes in 0 blocks" "$evidence/valgrind-extract.log"
    grep -q "ERROR SUMMARY: 3 errors from 3 contexts" "$evidence/valgrind-extract.log"
  '
