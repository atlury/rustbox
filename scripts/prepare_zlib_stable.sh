#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
base="$root/work/analysis/zlib-1.4/translations/c2rust-0.22.1"
input="$base/zlib-1.4-normalized-audit"
generic="$base/zlib-1.4-modernized-stable"
output="$base/zlib-1.4-stable"

"$root/scripts/modernize_c2rust_output.py" --input "$input" --output "$generic"
"$root/scripts/modernize_zlib_output.py" --input "$generic" --output "$output"
RUSTBOX_TOOL_IMAGE=rustbox-normalize:2026-11-19 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    crate=/work/work/analysis/zlib-1.4/translations/c2rust-0.22.1/zlib-1.4-stable
    python3 /work/scripts/check_cargo_crate.py \
      --crate "$crate" \
      --output "$crate/rustbox-cargo-check.json"
    cd "$crate"
    cargo build --release
  '
