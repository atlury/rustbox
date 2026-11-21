#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
base="$root/work/analysis/bc-1.08.2/translations/c2rust-0.22.1"
input="$base/bc-1.08.2-normalized-audit"
output="$base/bc-1.08.2-stable"

"$root/scripts/modernize_c2rust_output.py" --input "$input" --output "$output"

RUSTBOX_TOOL_IMAGE=rustbox-bc:2026-11-21 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    crate=/work/work/analysis/bc-1.08.2/translations/c2rust-0.22.1/bc-1.08.2-stable
    python3 /work/scripts/check_cargo_crate.py \
      --crate "$crate" --output "$crate/rustbox-cargo-check.json"
    cd "$crate"
    cargo build --release
  '
