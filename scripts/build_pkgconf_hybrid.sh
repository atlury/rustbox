#!/bin/sh
# SPDX-License-Identifier: ISC
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
mkdir -p "$root/build/pkgconf-3.0.11-hybrid"

RUSTBOX_TOOL_IMAGE=rustbox-normalize:2026-11-19 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    archive=/work/work/analysis/pkgconf-3.0.11/translations/c2rust-0.22.1/pkgconf-3.0.11-stable/target/release/libpkgconf_3_0_11_normalized_audit.a
    output=/work/build/pkgconf-3.0.11-hybrid/pkgconf-hybrid
    canonical_dir=/rustbox-pkgconf/normalized-clang-static
    clang-18 -O2 -g -ffunction-sections -fdata-sections \
      -Wl,--gc-sections -Wl,-Map,"$output.map" \
      -o "$output" /work/bridges/pkgconf_main.c "$archive" \
      -ldl -lpthread -lm
    cp "$output" "$output.stripped"
    strip --strip-all "$output.stripped"
    for tool in pkgconf bomtool pccritic spdxtool; do
      cp "$canonical_dir/$tool" "/work/build/pkgconf-3.0.11-hybrid/$tool.canonical-stripped"
      strip --strip-all "/work/build/pkgconf-3.0.11-hybrid/$tool.canonical-stripped"
    done
    size -A "$output" > "$output.sections"
    size -A "/work/build/pkgconf-3.0.11-hybrid/pkgconf.canonical-stripped" > "$output.canonical-sections"
    readelf -d "$output" > "$output.dynamic"
    sha256sum "$output" "$output.stripped" > "$output.sha256"
  '
