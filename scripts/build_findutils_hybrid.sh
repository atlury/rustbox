#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-findutils:2026-11-22 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    crate=/work/work/analysis/findutils-4.10.0/translations/c2rust-0.22.1/findutils-4.10.0-stable
    archive=$crate/target/release/libfindutils_4_10_0_combined.a
    database=/work/work/analysis/findutils-4.10.0/normalized/c2rust-compdb/compile_commands.json
    output=/rustbox-findutils/hybrid
    evidence=/work/work/analysis/findutils-4.10.0/hybrid
    canonical=/rustbox-findutils/normalized-gcc
    rm -rf "$output" "$evidence"
    mkdir -p "$output/find" "$output/xargs" "$output/locate" \
      "$output/c-residue" "$evidence"

    cd "$crate"
    cargo build --release
    python3 /work/scripts/build_findutils_c_residue.py \
      --database "$database" --output "$output/c-residue"
    residue="$output/c-residue/printf-args.o $output/c-residue/printf-parse.o $output/c-residue/vasnprintf.o"

    for specification in \
      find:find/find:rustbox_find_main \
      xargs:xargs/xargs:rustbox_xargs_main \
      locate:locate/locate:rustbox_locate_main \
      frcode:locate/frcode:rustbox_frcode_main
    do
      name=${specification%%:*}
      rest=${specification#*:}
      relative=${rest%:*}
      entry=${rest##*:}
      clang-18 -O2 -g -fno-omit-frame-pointer -ffunction-sections -fdata-sections \
        -DRUSTBOX_ENTRY="$entry" -Wl,--gc-sections \
        -Wl,-Map,"$evidence/$name.map" -o "$output/$relative" \
        /work/bridges/findutils_main.c $residue "$archive" \
        -ldl -lpthread -lm -lrt -lutil
      nm -g --defined-only "$output/$relative" >"$evidence/$name.symbols"
      readelf -d "$output/$relative" >"$evidence/$name.dynamic"
      size -A "$output/$relative" >"$evidence/$name.sections"
    done
    cp /rustbox-findutils/normalized-clang/locate/updatedb "$output/locate/updatedb"
    chmod +x "$output/locate/updatedb"
    cp "$output/c-residue/manifest.json" "$evidence/c-residue.json"

    python3 /work/tests/findutils-oracle-differential.py \
      --gcc-build "$canonical" --clang-build "$output" \
      --output "$evidence/differential.json"

    for item in find/find xargs/xargs locate/locate locate/frcode; do
      name=$(basename "$item")
      if test "$name" = frcode; then args=""; else args=--version; fi
      valgrind --leak-check=full --show-leak-kinds=all \
        --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
        --log-file="$evidence/valgrind-$name.log" \
        "$output/$item" $args </dev/null >"$evidence/valgrind-$name.out" 2>&1
      grep -q "ERROR SUMMARY: 0 errors" "$evidence/valgrind-$name.log"
    done
  '
