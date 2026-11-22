#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
base="$root/work/analysis/tar-1.35/translations/c2rust-0.22.1"
input="$base/tar-1.35-normalized-audit"
output="$base/tar-1.35-stable"

"$root/scripts/modernize_c2rust_output.py" --input "$input" --output "$output"
"$root/scripts/finalize_tar_stable.py" --crate "$output"

RUSTBOX_TOOL_IMAGE=rustbox-tar:2026-11-22 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    crate=/work/work/analysis/tar-1.35/translations/c2rust-0.22.1/tar-1.35-stable
    python3 /work/scripts/check_cargo_crate.py \
      --crate "$crate" --output "$crate/rustbox-cargo-check.json"
    cd "$crate"
    cargo build --release
  '
