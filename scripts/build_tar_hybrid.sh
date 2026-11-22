#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-tar:2026-11-22 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    crate=/work/work/analysis/tar-1.35/translations/c2rust-0.22.1/tar-1.35-stable
    archive=$crate/target/release/libtar_1_35_normalized_audit.a
    database=/work/work/analysis/tar-1.35/normalized/c2rust-compdb/compile_commands.json
    output=/rustbox-tar/hybrid
    evidence=/work/work/analysis/tar-1.35/hybrid
    artifacts=/work/work/analysis/tar-1.35/hybrid-artifacts
    canonical=/work/work/analysis/tar-1.35/normalized/clang-root
    rm -rf "$output" "$evidence" "$artifacts"
    mkdir -p "$output/usr/bin" "$output/usr/libexec" "$output/c-residue" \
      "$evidence" "$artifacts/c-residue"

    cd "$crate"
    cargo build --release
    python3 /work/scripts/build_tar_c_residue.py \
      --database "$database" --output "$output/c-residue"
    residue="$output/c-residue/human.o $output/c-residue/printf-args.o $output/c-residue/printf-parse.o $output/c-residue/vasnprintf.o"

    clang-18 -O2 -g -fno-omit-frame-pointer -ffunction-sections -fdata-sections \
      -DRUSTBOX_ENTRY=rustbox_tar_main -Wl,--gc-sections \
      -Wl,-Map,"$evidence/tar.map" -o "$output/usr/bin/tar" \
      /work/bridges/tar_main.c $residue "$archive" \
      -lacl -ldl -lpthread -lm -lrt -lutil
    clang-18 -O2 -g -fno-omit-frame-pointer -ffunction-sections -fdata-sections \
      -DRUSTBOX_ENTRY=rustbox_rmt_main -Wl,--gc-sections \
      -Wl,-Map,"$evidence/rmt.map" -o "$output/usr/libexec/rmt" \
      /work/bridges/tar_main.c $residue "$archive" \
      -lacl -ldl -lpthread -lm -lrt -lutil

    for utility in tar rmt; do
      if test "$utility" = tar; then binary=$output/usr/bin/tar
      else binary=$output/usr/libexec/rmt; fi
      cp "$binary" "$artifacts/$utility"
      cp "$binary" "$artifacts/$utility.stripped"
      strip --strip-all "$artifacts/$utility.stripped"
      readelf -d "$binary" > "$evidence/$utility.dynamic"
      size -A "$binary" > "$evidence/$utility.sections"
      nm -g --defined-only "$binary" > "$evidence/$utility.symbols"
    done
    cp "$output/c-residue/"*.o "$artifacts/c-residue/"
    cp "$output/c-residue/manifest.json" "$artifacts/c-residue/manifest.json"
    cp "$output/c-residue/manifest.json" "$evidence/c-residue.json"

    python3 /work/tests/tar-oracle-differential.py \
      --gcc-root "$canonical" --clang-root "$output" \
      --output "$evidence/differential.json"

    scratch=$(mktemp -d /rustbox-tar/tar-hybrid-valgrind.XXXXXX)
    trap '"'"'rm -rf "$scratch"'"'"' EXIT HUP INT TERM
    mkdir "$scratch/source" "$scratch/extracted"
    printf "hybrid tar payload\n" >"$scratch/source/payload"
    dd if=/dev/zero of="$scratch/source/sparse" bs=1 count=0 \
      seek=1048576 2>/dev/null
    ln -s payload "$scratch/source/link"
    tar_bin=$output/usr/bin/tar
    rmt_bin=$output/usr/libexec/rmt
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
    then extract_status=0; else extract_status=$?; fi
    test "$extract_status" -eq 0
    if printf "X\n" | valgrind --leak-check=full --show-leak-kinds=all \
        --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
        --log-file="$evidence/valgrind-rmt.log" "$rmt_bin" \
        >"$evidence/rmt-invalid.stdout" 2>"$evidence/rmt-invalid.stderr"
    then rmt_status=0; else rmt_status=$?; fi
    test "$rmt_status" -eq 1
    cmp "$scratch/source/payload" "$scratch/extracted/payload"
    cmp "$scratch/source/sparse" "$scratch/extracted/sparse"
    test "$(readlink "$scratch/extracted/link")" = payload
    for operation in create list extract rmt; do
      grep -q "ERROR SUMMARY: 0 errors" "$evidence/valgrind-$operation.log"
      grep -q "definitely lost: 0 bytes in 0 blocks" "$evidence/valgrind-$operation.log"
      grep -q "indirectly lost: 0 bytes in 0 blocks" "$evidence/valgrind-$operation.log"
      grep -q "possibly lost: 0 bytes in 0 blocks" "$evidence/valgrind-$operation.log"
    done
  '
