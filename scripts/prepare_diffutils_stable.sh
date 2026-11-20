#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
base="$root/work/analysis/diffutils-3.12/translations/c2rust-0.22.1"
input="$base/diffutils-3.12-normalized-audit"
output="$base/diffutils-3.12-stable"

"$root/scripts/modernize_c2rust_output.py" --input "$input" --output "$output"

RUSTBOX_TOOL_IMAGE=rustbox-diffutils:2026-11-20 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    crate=/work/work/analysis/diffutils-3.12/translations/c2rust-0.22.1/diffutils-3.12-stable
    python3 /work/scripts/check_cargo_crate.py \
      --crate "$crate" --output "$crate/rustbox-cargo-check.json"
    cd "$crate"
    cargo build --release
  '
