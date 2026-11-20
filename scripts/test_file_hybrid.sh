#!/bin/sh
# SPDX-License-Identifier: BSD-2-Clause
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
"$root/scripts/build_file_hybrid.sh"

RUSTBOX_TOOL_IMAGE=rustbox-file:2026-11-20 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    output=/work/work/analysis/file-5.48/hybrid
    hybrid=/work/build/file-5.48-hybrid/file
    archive=/work/work/analysis/file-5.48/translations/c2rust-0.22.1/file-5.48-stable/target/release/libfile_5_48_normalized_audit.a
    source=/rustbox-file/normalized-source
    build=/rustbox-file/normalized-gcc
    magic=$build/magic/magic
    libraries="-lbz2 -llz -llzma -lseccomp -lz -lzstd -ldl -lpthread -lm"
    rm -rf "$output"
    mkdir -p "$output"

    gcc -o "$output/test-rust" "$build/tests/test-test.o" "$archive" $libraries
    : > "$output/upstream-tests.log"
    fixture_count=0
    for input in "$source"/tests/*.testfile; do
      test_prefix=${input%.testfile}
      fixture_magic=
      for candidate in $(eval echo "${test_prefix}"\*.magic); do
        test -f "$candidate" || continue
        if test -z "$fixture_magic"; then
          fixture_magic=$candidate
        else
          fixture_magic=$fixture_magic:$candidate
        fi
      done
      test -n "$fixture_magic" || fixture_magic=$magic
      flags=-e
      test ! -f "${test_prefix}.flags" || flags=$flags$(cat "${test_prefix}.flags")
      echo "Running test: $test_prefix" >> "$output/upstream-tests.log"
      TZ=UTC MAGIC="$fixture_magic" "$output/test-rust" "$flags" \
        "$input" "${test_prefix}.result" >> "$output/upstream-tests.log" 2>&1
      fixture_count=$((fixture_count + 1))
    done
    test "$fixture_count" -eq 83

    python3 /work/tests/file-oracle-differential.py \
      --gcc /rustbox-file/canonical-gcc/src/file \
      --clang "$hybrid" --magic /rustbox-file/canonical-gcc/magic/magic \
      --upstream-tests "$source/tests" \
      --output "$output/differential.json"

    printf "rustbox translated file\n" > "$output/valgrind-input.txt"
    valgrind --leak-check=full --show-leak-kinds=all \
      --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
      --log-file="$output/valgrind-cli.log" \
      "$hybrid" --no-sandbox -m "$magic" "$output/valgrind-input.txt" \
      > "$output/valgrind-cli.out"
    grep -q "ERROR SUMMARY: 0 errors" "$output/valgrind-cli.log"
    grep -q "All heap blocks were freed -- no leaks are possible" \
      "$output/valgrind-cli.log"
  '
