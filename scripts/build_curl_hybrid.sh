#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-curl:2026-11-23 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    crate=/work/work/analysis/curl-8.23.0/translations/c2rust-0.22.1/curl-8.23.0-stable
    archive=$crate/target/release/libcurl_8_23_0_normalized_audit.a
    database=/work/work/analysis/curl-8.23.0/normalized/clang-compile-commands.json
    output=/rustbox-curl/hybrid
    evidence=/work/work/analysis/curl-8.23.0/hybrid
    artifacts=/work/work/analysis/curl-8.23.0/hybrid-artifacts
    oracle=/work/work/analysis/curl-8.23.0/oracle
    rm -rf "$output" "$evidence" "$artifacts"
    mkdir -p "$output/c-residue" "$evidence" "$artifacts/c-residue"

    cd "$crate"
    cargo build --release
    python3 /work/scripts/build_curl_c_residue.py \
      --database "$database" --output "$output/c-residue"

    clang-18 -O2 -g -fno-omit-frame-pointer -ffunction-sections -fdata-sections \
      -Wl,--gc-sections -Wl,-Map,"$evidence/curl.map" \
      -o "$output/curl" /work/bridges/curl_main.c \
      "$output/c-residue/mprintf.o" "$archive" \
      -ldl -lpthread -lm -lrt

    cp "$output/curl" "$artifacts/curl"
    cp "$output/curl" "$artifacts/curl.stripped"
    strip --strip-all "$artifacts/curl.stripped"
    readelf -d "$output/curl" >"$evidence/curl.dynamic"
    size -A "$output/curl" >"$evidence/curl.sections"
    nm -g --defined-only "$output/curl" >"$evidence/curl.symbols"
    test "$(awk '\''$NF == "rustbox_curl_main" { n++ } END { print n+0 }'\'' "$evidence/curl.symbols")" -eq 1
    cp "$output/c-residue/mprintf.o" "$artifacts/c-residue/"
    cp "$output/c-residue/manifest.json" "$artifacts/c-residue/manifest.json"
    cp "$output/c-residue/manifest.json" "$evidence/c-residue.json"

    python3 /work/tests/curl-oracle-differential.py \
      --gcc "$oracle/curl-gcc" --clang "$output/curl" \
      --output "$evidence/differential.json"

    valgrind --leak-check=full --show-leak-kinds=all \
      --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
      --log-file="$evidence/valgrind-version.log" \
      "$output/curl" --version >"$evidence/valgrind-version.out"
    printf "rustbox-curl-hybrid-payload\n" >"$evidence/file-input"
    valgrind --leak-check=full --show-leak-kinds=all \
      --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
      --log-file="$evidence/valgrind-file.log" \
      "$output/curl" --silent --show-error \
        "file://$evidence/file-input" >"$evidence/valgrind-file.out"
    cmp "$evidence/file-input" "$evidence/valgrind-file.out"
    for operation in version file; do
      grep -q "ERROR SUMMARY: 0 errors" "$evidence/valgrind-$operation.log"
      if ! grep -q "All heap blocks were freed -- no leaks are possible" \
          "$evidence/valgrind-$operation.log"; then
        grep -q "definitely lost: 0 bytes in 0 blocks" "$evidence/valgrind-$operation.log"
        grep -q "indirectly lost: 0 bytes in 0 blocks" "$evidence/valgrind-$operation.log"
        grep -q "possibly lost: 0 bytes in 0 blocks" "$evidence/valgrind-$operation.log"
      fi
    done
  '
