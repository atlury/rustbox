#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
base="$root/work/analysis/kmod-34.3/translations/c2rust-0.22.1"
audit="$base/kmod-34.3-normalized-audit"
stable="$base/kmod-34.3-stable"

python3 -B "$root/scripts/modernize_c2rust_output.py" \
  --input "$audit" --output "$stable"
python3 -B "$root/scripts/finalize_kmod_stable.py" --crate "$stable"

RUSTBOX_TOOL_IMAGE=rustbox-kmod:2026-11-24 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    crate=/work/work/analysis/kmod-34.3/translations/c2rust-0.22.1/kmod-34.3-stable
    export CARGO_TARGET_DIR=/rustbox-kmod/cargo-target-stable
    python3 /work/scripts/check_cargo_crate.py \
      --crate "$crate" --output "$crate/rustbox-cargo-check.json"
    cd "$crate"
    cargo build --release
  '
