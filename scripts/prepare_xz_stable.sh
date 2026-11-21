#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
base="$root/work/analysis/xz-5.8.4/translations/c2rust-0.22.1"
input="$base/xz-5.8.4-normalized-audit"
output="$base/xz-5.8.4-stable"

"$root/scripts/modernize_c2rust_output.py" --input "$input" --output "$output"
"$root/scripts/repair_xz_translation.py" --crate "$output"

RUSTBOX_TOOL_IMAGE=rustbox-xz:2026-11-22 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    crate=/work/work/analysis/xz-5.8.4/translations/c2rust-0.22.1/xz-5.8.4-stable
    python3 /work/scripts/check_cargo_crate.py \
      --crate "$crate" --output "$crate/rustbox-cargo-check.json"
    cd "$crate"
    cargo build --release
  '
