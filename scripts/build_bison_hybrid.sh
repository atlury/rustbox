#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-bison:2026-11-23 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    crate=/work/work/analysis/bison-3.8.2/translations/c2rust-0.22.1/bison-3.8.2-stable
    archive=$crate/target/release/libbison_3_8_2_normalized_audit.a
    database=/work/work/analysis/bison-3.8.2/normalized/c2rust-compdb/compile_commands.json
    output=/rustbox-bison/hybrid
    evidence=/work/work/analysis/bison-3.8.2/hybrid
    artifacts=/work/work/analysis/bison-3.8.2/hybrid-artifacts
    canonical=/work/work/analysis/bison-3.8.2/normalized/clang-root
    oracle=/work/work/analysis/bison-3.8.2/oracle/gcc-root
    source=/work/work/upstream/bison-3.8.2
    rm -rf "$output" "$evidence" "$artifacts"
    mkdir -p "$output/usr/bin" "$output/usr/share" "$output/c-residue" \
      "$evidence" "$artifacts/c-residue"

    cd "$crate"
    cargo build --release
    python3 /work/scripts/build_bison_c_residue.py \
      --database "$database" --output "$output/c-residue"
    residue="$output/c-residue/printf-args.o $output/c-residue/printf-frexpl.o $output/c-residue/printf-parse.o $output/c-residue/vasnprintf.o"

    clang-18 -O2 -g -fno-omit-frame-pointer -ffunction-sections -fdata-sections \
      -Wl,--gc-sections -Wl,-Map,"$evidence/bison.map" \
      -o "$output/usr/bin/bison" /work/bridges/bison_main.c \
      $residue "$archive" -ldl -lpthread -lm -lrt
    ln -s bison "$output/usr/bin/yacc"
    cp -a "$canonical/usr/share/bison" "$output/usr/share/"

    cp "$output/usr/bin/bison" "$artifacts/bison"
    cp "$output/usr/bin/bison" "$artifacts/bison.stripped"
    strip --strip-all "$artifacts/bison.stripped"
    readelf -d "$output/usr/bin/bison" >"$evidence/bison.dynamic"
    size -A "$output/usr/bin/bison" >"$evidence/bison.sections"
    nm -g --defined-only "$output/usr/bin/bison" >"$evidence/bison.symbols"
    test "$(awk '\''$NF == "rustbox_bison_main" { n++ } END { print n+0 }'\'' "$evidence/bison.symbols")" -eq 1
    test "$(awk '\''$NF == "rustbox_yacc_main" { n++ } END { print n+0 }'\'' "$evidence/bison.symbols")" -eq 1
    cp "$output/c-residue/"*.o "$artifacts/c-residue/"
    cp "$output/c-residue/manifest.json" "$artifacts/c-residue/manifest.json"
    cp "$output/c-residue/manifest.json" "$evidence/c-residue.json"

    python3 /work/tests/bison-oracle-differential.py \
      --gcc "$oracle/usr/bin/bison" \
      --gcc-datadir "$oracle/usr/share/bison" \
      --clang "$output/usr/bin/bison" \
      --clang-datadir "$output/usr/share/bison" \
      --source "$source" --output "$evidence/differential.json"
    python3 /work/tests/bison-yacc-frontend.py \
      --canonical "$oracle/usr/bin/yacc" \
      --canonical-datadir "$oracle/usr/share/bison" \
      --hybrid "$output/usr/bin/yacc" \
      --hybrid-datadir "$output/usr/share/bison" \
      --output "$evidence/yacc-frontend.json"

    BISON_PKGDATADIR="$output/usr/share/bison" \
      valgrind --leak-check=full --show-leak-kinds=all \
      --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
      --log-file="$evidence/valgrind-help.log" \
      "$output/usr/bin/bison" --help >/dev/null
    grep -q "ERROR SUMMARY: 0 errors" "$evidence/valgrind-help.log"
    grep -q "definitely lost: 0 bytes in 0 blocks" "$evidence/valgrind-help.log"
    grep -q "indirectly lost: 0 bytes in 0 blocks" "$evidence/valgrind-help.log"
    grep -q "possibly lost: 0 bytes in 0 blocks" "$evidence/valgrind-help.log"
  '
