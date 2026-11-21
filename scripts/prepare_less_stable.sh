#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
base="$root/work/analysis/less-710/translations/c2rust-0.22.1"
input="$base/less-710-normalized-audit"
output="$base/less-710-stable"

"$root/scripts/modernize_c2rust_output.py" --input "$input" --output "$output"
"$root/scripts/repair_less_translation.py" \
  --crate "$output" \
  --output "$output/rustbox-less-repairs.json"

RUSTBOX_TOOL_IMAGE=rustbox-less:2026-11-22 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    crate=/work/work/analysis/less-710/translations/c2rust-0.22.1/less-710-stable
    python3 /work/scripts/check_cargo_crate.py \
      --crate "$crate" --output "$crate/rustbox-cargo-check.json"
    cd "$crate"
    cargo build --release
  '
