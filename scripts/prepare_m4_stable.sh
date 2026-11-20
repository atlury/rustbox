#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
base="$root/work/analysis/m4-1.4.21/translations/c2rust-0.22.1"
input="$base/m4-1.4.21-normalized-audit"
output="$base/m4-1.4.21-stable"

"$root/scripts/modernize_c2rust_output.py" --input "$input" --output "$output"

RUSTBOX_TOOL_IMAGE=rustbox-normalize:2026-11-19 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    crate=/work/work/analysis/m4-1.4.21/translations/c2rust-0.22.1/m4-1.4.21-stable
    python3 /work/scripts/check_cargo_crate.py \
      --crate "$crate" --output "$crate/rustbox-cargo-check.json"
    cd "$crate"
    cargo build --release
  '
