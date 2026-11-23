#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-kmod:2026-11-24 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    crate=/work/work/analysis/kmod-34.3/translations/c2rust-0.22.1/kmod-34.3-stable
    archive=$crate/target/release/libkmod_34_3_normalized_audit.a
    output=/rustbox-kmod/hybrid
    evidence=/work/work/analysis/kmod-34.3/hybrid
    oracle=/rustbox-kmod/oracle-gcc

    rm -rf "$output" "$evidence"
    mkdir -p "$output" "$evidence"
    cd "$crate"
    cargo build --release

    clang-18 -O2 -g -fno-omit-frame-pointer \
      -ffunction-sections -fdata-sections -Wl,--gc-sections \
      -Wl,-Map,"$evidence/kmod.map" \
      -o "$output/kmod" /work/bridges/kmod_main.c "$archive" \
      -lzstd -llzma -lz -lcrypto -ldl -lpthread -lm -lrt
    for name in depmod insmod lsmod modinfo modprobe rmmod; do
      ln -s kmod "$output/$name"
    done

    readelf -d "$output/kmod" >"$evidence/kmod.dynamic"
    size -A "$output/kmod" >"$evidence/kmod.sections"
    nm -g --defined-only "$output/kmod" >"$evidence/kmod.symbols"
    test "$(awk '\''$NF == "rustbox_kmod_main" { n++ } END { print n+0 }'\'' \
      "$evidence/kmod.symbols")" -eq 1
    cp "$output/kmod" "$evidence/kmod"
    cp "$output/kmod" "$evidence/kmod.stripped"
    strip --strip-all "$evidence/kmod.stripped"

    python3 /work/tests/kmod-oracle-differential.py \
      --gcc-root "$oracle" --clang-root "$output" \
      --output "$evidence/differential.json"
    for name in kmod depmod insmod lsmod modinfo modprobe rmmod; do
      valgrind --leak-check=full --show-leak-kinds=all \
        --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
        --log-file="$evidence/valgrind-$name.log" \
        "$output/$name" --version >"$evidence/valgrind-$name.out"
      grep -q "ERROR SUMMARY: 0 errors" "$evidence/valgrind-$name.log"
      if ! grep -q "All heap blocks were freed -- no leaks are possible" \
          "$evidence/valgrind-$name.log"; then
        grep -q "definitely lost: 0 bytes in 0 blocks" "$evidence/valgrind-$name.log"
        grep -q "indirectly lost: 0 bytes in 0 blocks" "$evidence/valgrind-$name.log"
        grep -q "possibly lost: 0 bytes in 0 blocks" "$evidence/valgrind-$name.log"
      fi
    done
    chmod -R a+rwX "$evidence"
  '
