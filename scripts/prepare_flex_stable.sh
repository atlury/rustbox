#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
base="$root/work/analysis/flex-2.6.4/translations/c2rust-0.22.1"
audit="$base/flex-2.6.4-normalized-audit"
stable="$base/flex-2.6.4-stable"

python3 -B "$root/scripts/modernize_c2rust_output.py" \
  --input "$audit" --output "$stable"

RUSTBOX_TOOL_IMAGE=rustbox-flex:2026-11-22 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    crate=/work/work/analysis/flex-2.6.4/translations/c2rust-0.22.1/flex-2.6.4-stable
    cd "$crate"
    cargo check --release >cargo-check.log 2>&1
    cargo build --release >cargo-build.log 2>&1
    test "$(nm -g --defined-only target/release/libflex_2_6_4_normalized_audit.a \
      | grep -c " rustbox_flex_main$")" -eq 1
  '
