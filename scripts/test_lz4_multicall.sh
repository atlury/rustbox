#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-e2fsprogs:2026-11-24 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    output=/work/work/analysis/lz4-1.11.1/multicall
    rustbox=/rustbox-coreutils/canonical-clang-no-security-compdb/src/rustbox
    canonical=/work/work/analysis/lz4-1.11.1/normalized/gcc
    dispatch=/rustbox-lz4/multicall-dispatch
    source=/rustbox-lz4/multicall-test-source
    rm -rf "$output" "$dispatch" "$source"
    mkdir -p "$output" "$dispatch"

    for utility in lz4 lz4c lz4cat unlz4; do
      ln -s "$rustbox" "$dispatch/$utility"
    done
    python3 /work/tests/lz4-oracle-differential.py \
      --gcc-directory "$canonical" --clang-directory "$dispatch" \
      --output "$output/differential.json"

    cp -a /rustbox-lz4/normalized-source "$source"
    make -j"$(nproc)" -C "$source/tests" datagen checkFrame
    cp "$rustbox" "$source/programs/lz4"
    for alias in lz4c lz4cat unlz4; do
      ln -sf lz4 "$source/programs/$alias"
    done
    if make -j"$(nproc)" -C "$source/tests" -o lz4 \
        LZ4="$source/programs/lz4" test-lz4-essentials \
        >"$output/upstream-tests.log" 2>&1
    then
      cat "$output/upstream-tests.log"
    else
      status=$?
      cat "$output/upstream-tests.log"
      exit "$status"
    fi

    cd /rustbox-lz4
    printf "the quick brown fox\n%.0s" $(seq 1 1024) > multicall-valgrind-input
    "$canonical/lz4" -f multicall-valgrind-input multicall-valgrind-input.canonical.lz4
    valgrind --leak-check=full --show-leak-kinds=all \
      --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
      --log-file="$output/valgrind-compress.log" \
      "$rustbox" lz4 -f multicall-valgrind-input multicall-valgrind-input.multicall.lz4
    valgrind --leak-check=full --show-leak-kinds=all \
      --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
      --xtree-memory=full --xtree-memory-file="$output/decompress-multicall.xtree" \
      --log-file="$output/valgrind-decompress.log" \
      "$rustbox" lz4 -d -f multicall-valgrind-input.canonical.lz4 \
        multicall-valgrind-output
    valgrind --leak-check=full --show-leak-kinds=all \
      --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
      --xtree-memory=full --xtree-memory-file="$output/decompress-canonical.xtree" \
      --log-file="$output/valgrind-decompress-canonical.log" \
      "$canonical/lz4" -d -f multicall-valgrind-input.canonical.lz4 multicall-valgrind-output.canonical
    cmp multicall-valgrind-output.canonical multicall-valgrind-output
    for implementation in canonical multicall; do
      callgrind_annotate --inclusive=no --show=totB,totBk --threshold=100 --show-percs=no --auto=no \
        "$output/decompress-$implementation.xtree" >"$output/decompress-$implementation-sites"
    done
    for operation in compress decompress; do
      grep -q "ERROR SUMMARY: 0 errors" "$output/valgrind-$operation.log"
      grep -q "All heap blocks were freed -- no leaks are possible" \
        "$output/valgrind-$operation.log"
      sed -n "/HEAP SUMMARY/,+2p" "$output/valgrind-$operation.log" \
        | sed "s/^==[0-9]*== *//" >"$output/valgrind-$operation-heap"
    done
    cat >"$output/valgrind-compress-expected" <<EOF
HEAP SUMMARY:
in use at exit: 0 bytes in 0 blocks
total heap usage: 9 allocs, 9 frees, 8,410,567 bytes allocated
EOF
    # Two glibc worker TLS allocations use 368 bytes each in the 499-name ELF.
    cat >"$output/valgrind-decompress-expected" <<EOF
HEAP SUMMARY:
in use at exit: 0 bytes in 0 blocks
total heap usage: 29 allocs, 29 frees, 29,633,348 bytes allocated
EOF
    cmp "$output/valgrind-compress-heap" "$output/valgrind-compress-expected"
    cmp "$output/valgrind-decompress-heap" "$output/valgrind-decompress-expected"
    cmp multicall-valgrind-input.canonical.lz4 multicall-valgrind-input.multicall.lz4
    cmp multicall-valgrind-input multicall-valgrind-output
  '
