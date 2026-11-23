#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-procps:2026-11-24 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    crate=/work/work/analysis/procps-ng-4.0.7/translations/c2rust-0.22.1/procps-ng-4.0.7-nightly
    archive=$crate/target/release/libprocps_ng_4_0_7_normalized_audit.a
    output=/rustbox-procps/hybrid
    evidence=/work/work/analysis/procps-ng-4.0.7/hybrid
    oracle=/rustbox-procps/programs-gcc
    oracle_library=/rustbox-procps/oracle-gcc/library/.libs

    rm -rf "$output" "$evidence"
    mkdir -p "$output" "$evidence"
    cd "$crate"
    RUSTUP_TOOLCHAIN=nightly-2023-04-15 cargo build --release

    clang-18 -O2 -g -fno-omit-frame-pointer \
      -ffunction-sections -fdata-sections -Wl,--gc-sections \
      -Wl,-Map,"$evidence/procps.map" \
      -o "$output/procps" /work/bridges/procps_main.c "$archive" \
      -lncursesw -ltinfo -ldl -lpthread -lm -lrt
    for name in free hugetop kill pgrep pidof pidwait pkill pmap ps pwdx \
      skill slabtop snice sysctl tload top uptime vmstat w watch; do
      ln -s procps "$output/$name"
    done

    readelf -d "$output/procps" >"$evidence/procps.dynamic"
    size -A "$output/procps" >"$evidence/procps.sections"
    nm -g --defined-only "$output/procps" >"$evidence/procps.symbols"
    for symbol in free hugetop kill pgrep pidof pmap ps pwdx skill slabtop \
      sysctl tload top uptime vmstat w watch; do
      test "$(awk -v wanted="rustbox_procps_${symbol}_main" \
        '\''$NF == wanted { n++ } END { print n+0 }'\'' \
        "$evidence/procps.symbols")" -eq 1
    done
    cp "$output/procps" "$evidence/procps"
    cp "$output/procps" "$evidence/procps.stripped"
    strip --strip-all "$evidence/procps.stripped"

    python3 /work/tests/procps-oracle-differential.py \
      --gcc-root "$oracle" --gcc-library "$oracle_library" \
      --clang-root "$output" --clang-library "$crate/target/release" \
      --output "$evidence/differential.json"
    for name in free hugetop kill pgrep pidof pidwait pkill pmap ps pwdx \
      skill slabtop snice sysctl tload top uptime vmstat w watch; do
      valgrind --leak-check=full --show-leak-kinds=all \
        --errors-for-leak-kinds=definite,indirect,possible \
        --log-file="$evidence/valgrind-$name.log" \
        "$output/$name" --version >"$evidence/valgrind-$name.out" 2>&1 || true
    done
    chmod -R a+rwX "$evidence"
  '
