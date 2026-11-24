#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
base="$root/work/analysis/shadow-4.20.4/translations/c2rust-0.22.1"
audit="$base/shadow-4.20.4-normalized-audit"
nightly="$base/shadow-4.20.4-nightly"

python3 -B "$root/scripts/finalize_shadow_nightly.py" \
  --input "$audit" --output "$nightly"

RUSTBOX_TOOL_IMAGE=rustbox-shadow:2026-11-24 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    crate=/work/work/analysis/shadow-4.20.4/translations/c2rust-0.22.1/shadow-4.20.4-nightly
    python3 /work/scripts/check_cargo_crate.py \
      --crate "$crate" --output "$crate/rustbox-cargo-check.json" \
      --toolchain nightly-2023-04-15
    cd "$crate"
    RUSTUP_TOOLCHAIN=nightly-2023-04-15 cargo build --release
  '
