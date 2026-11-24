#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-shadow:2026-11-24 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    crate=/work/work/analysis/shadow-4.20.4/translations/c2rust-0.22.1/shadow-4.20.4-nightly
    archive=$crate/target/release/libshadow_4_20_4_normalized_audit.a
    output=/rustbox-shadow/hybrid
    evidence=/work/work/analysis/shadow-4.20.4/hybrid
    oracle=/rustbox-shadow/programs-gcc
    programs="chage chfn chgpasswd chpasswd chsh faillog getsubids gpasswd groupadd groupdel groupmod grpck grpconv grpunconv lastlog login newgidmap newgrp newuidmap newusers nologin passwd pwck pwconv pwunconv su useradd userdel usermod vipw sg vigr"
    engines="chage chfn chgpasswd chpasswd chsh faillog getsubids gpasswd groupadd groupdel groupmod grpck grpconv grpunconv lastlog login newgidmap newgrp newuidmap newusers nologin passwd pwck pwconv pwunconv su useradd userdel usermod vipw"

    rm -rf "$output" "$evidence"
    mkdir -p "$output" "$evidence"
    cd "$crate"
    RUSTUP_TOOLCHAIN=nightly-2023-04-15 cargo build --release

    clang-18 -O2 -g -fno-omit-frame-pointer \
      -ffunction-sections -fdata-sections -Wl,--gc-sections \
      -Wl,-Map,"$evidence/shadow.map" \
      -o "$output/shadow" /work/bridges/shadow_main.c "$archive" \
      -lcrypt -ldl -lpthread -lm -lrt
    for name in $programs; do
      ln -s shadow "$output/$name"
    done

    readelf -d "$output/shadow" >"$evidence/shadow.dynamic"
    size -A "$output/shadow" >"$evidence/shadow.sections"
    nm -g --defined-only "$output/shadow" >"$evidence/shadow.symbols"
    for engine in $engines; do
      test "$(awk -v wanted="rustbox_shadow_${engine}_main" \
        '\''$NF == wanted { n++ } END { print n+0 }'\'' \
        "$evidence/shadow.symbols")" -eq 1
    done
    cp "$output/shadow" "$evidence/shadow"
    cp "$output/shadow" "$evidence/shadow.stripped"
    strip --strip-all "$evidence/shadow.stripped"

    python3 /work/tests/shadow-oracle-differential.py \
      --gcc-root "$oracle" --clang-root "$output" \
      --output "$evidence/differential.json"
    for name in $programs; do
      valgrind --leak-check=full --show-leak-kinds=all \
        --errors-for-leak-kinds=definite,indirect,possible \
        --log-file="$evidence/valgrind-$name.log" \
        "$output/$name" --version >"$evidence/valgrind-$name.out" 2>&1 || true
    done
    chmod -R a+rwX "$evidence"
  '
