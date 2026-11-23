#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-inetutils:2026-11-23 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    base=/work/work/analysis/inetutils-2.8/program-translations
    target=$base/cargo-target
    output=/rustbox-inetutils/program-hybrid
    evidence=/work/work/analysis/inetutils-2.8/program-hybrids
    mkdir -p "$output" "$evidence"
    export CARGO_TARGET_DIR="$target"

    for name in rexec tftp traceroute ifconfig ping ping6; do
      crate=$base/$name/$name-stable
      python3 /work/scripts/check_cargo_crate.py \
        --crate "$crate" --output "$evidence/$name-cargo-check.json"
      cd "$crate"
      cargo build --release
      clang-18 -O2 -g -fno-omit-frame-pointer \
        -ffunction-sections -fdata-sections -Wl,--gc-sections \
        -Wl,-Map,"$evidence/$name.map" \
        -DRUSTBOX_INETUTILS_ENTRY=rustbox_inetutils_${name}_main \
        -o "$output/$name" /work/bridges/inetutils_program_main.c \
        "$target/release/lib${name}_audit.a" \
        -ldl -lpthread -lm -lrt -lutil
      nm -g --defined-only "$output/$name" >"$evidence/$name.symbols"
      test "$(awk -v symbol="rustbox_inetutils_${name}_main" \
        '\''$NF == symbol { n++ } END { print n+0 }'\'' \
        "$evidence/$name.symbols")" -eq 1
    done
    chmod -R a+rwX "$output" "$evidence" "$target"
  '
