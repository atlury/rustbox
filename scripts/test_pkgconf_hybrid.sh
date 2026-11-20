#!/bin/sh
# SPDX-License-Identifier: ISC
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
"$root/scripts/build_pkgconf_hybrid.sh"

RUSTBOX_TOOL_IMAGE=rustbox-normalize:2026-11-19 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    output=/work/work/analysis/pkgconf-3.0.11/hybrid
    hybrid=/work/build/pkgconf-3.0.11-hybrid/pkgconf-hybrid
    archive=/work/work/analysis/pkgconf-3.0.11/translations/c2rust-0.22.1/pkgconf-3.0.11-stable/target/release/libpkgconf_3_0_11_normalized_audit.a
    build=/rustbox-pkgconf/normalized-gcc-static
    source=/rustbox-pkgconf/normalized-source
    bindir=$output/bin
    canonical=$output/canonical-bin
    api=$output/api-rust
    fuzz=$output/fuzz-rust
    rm -rf "$output"
    mkdir -p "$bindir" "$canonical" "$api" "$fuzz"

    for name in pkgconf pkg-config bomtool pccritic spdxtool; do
      ln -s "$hybrid" "$bindir/$name"
    done
    for name in pkgconf bomtool pccritic spdxtool; do
      ln -s /rustbox-pkgconf/normalized-clang-static/$name "$canonical/$name"
    done
    ln -s /rustbox-pkgconf/normalized-clang-static/pkgconf "$canonical/pkg-config"

    : > "$output/fixture-tests.log"
    fixture_count=0
    for suite in "$source"/t/*; do
      test -d "$suite" || continue
      echo "== $(basename "$suite") ==" >> "$output/fixture-tests.log"
      "$build/test-runner" --test-fixtures "$source/tests" \
        --tool-dir "$bindir" "$suite" >> "$output/fixture-tests.log" 2>&1
      fixture_count=$((fixture_count + 1))
    done
    test "$fixture_count" -eq 14

    : > "$output/api-tests.log"
    api_count=0
    for dir in "$build"/test-api-*.p; do
      name=$(basename "$dir" .p)
      object=$(find "$dir" -maxdepth 1 -name "tests_api_*.o" -print)
      test -n "$object"
      test "$(printf "%s\n" "$object" | wc -l)" -eq 1
      gcc -o "$api/$name" "$object" "$archive" \
        -ldl -lrt -lpthread -lgcc_s -lc -lm -lutil
      echo "== $name ==" >> "$output/api-tests.log"
      "$api/$name" >> "$output/api-tests.log" 2>&1
      api_count=$((api_count + 1))
    done
    test "$api_count" -eq 16

    for kind in parser solver; do
      objects="$build/fuzz-replay-$kind.p/fuzzer_replay.c.o $build/fuzz-replay-$kind.p/fuzzer_${kind}-fuzzer.c.o $build/fuzz-replay-$kind.p/fuzzer_alloc-inject.c.o"
      gcc -o "$fuzz/fuzz-replay-$kind" $objects "$archive" \
        -Wl,--wrap=malloc -Wl,--wrap=calloc -Wl,--wrap=realloc \
        -Wl,--wrap=reallocarray -Wl,--wrap=strdup -Wl,--wrap=strndup \
        -ldl -lrt -lpthread -lgcc_s -lc -lm -lutil
    done
    "$fuzz/fuzz-replay-parser" "$source/tests/lib1" > "$output/fuzz-parser.log" 2>&1
    echo "parser: PASS" > "$output/fuzz-tests.log"
    "$fuzz/fuzz-replay-solver" "$source/fuzzer/solver-corpus" > "$output/fuzz-solver.log" 2>&1
    echo "solver: PASS" >> "$output/fuzz-tests.log"

    python3 /work/tests/pkgconf-differential.py \
      --canonical-dir "$canonical" --hybrid-dir "$bindir" \
      --output "$output/differential.json"

    verify_valgrind()
    {
      log=$1
      grep -q "ERROR SUMMARY: 0 errors" "$log"
      if grep -q "All heap blocks were freed -- no leaks are possible" "$log"; then
        return 0
      fi
      grep -q "definitely lost: 0 bytes in 0 blocks" "$log"
      grep -q "indirectly lost: 0 bytes in 0 blocks" "$log"
      grep -q "possibly lost: 0 bytes in 0 blocks" "$log"
    }

    for name in pkgconf pkg-config bomtool pccritic spdxtool; do
      valgrind --leak-check=full --show-leak-kinds=all \
        --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
        --log-file="$output/valgrind-$name.log" "$bindir/$name" --help \
        >/dev/null 2>/dev/null
      verify_valgrind "$output/valgrind-$name.log"
    done
    valgrind --leak-check=full --show-leak-kinds=all \
      --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
      --log-file="$output/valgrind-api-buffer.log" "$api/test-api-buffer" \
      >/dev/null 2>/dev/null
    verify_valgrind "$output/valgrind-api-buffer.log"
  '
