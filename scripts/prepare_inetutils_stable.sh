#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
base="$root/work/analysis/inetutils-2.8/translations/c2rust-0.22.1"
audit="$base/inetutils-2.8-normalized-audit"
stable="$base/inetutils-2.8-stable"

python3 -B "$root/scripts/modernize_c2rust_output.py" \
  --input "$audit" --output "$stable"
python3 -B "$root/scripts/finalize_inetutils_stable.py" --crate "$stable"

RUSTBOX_TOOL_IMAGE=rustbox-inetutils:2026-11-23 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    crate=/work/work/analysis/inetutils-2.8/translations/c2rust-0.22.1/inetutils-2.8-stable
    export CARGO_TARGET_DIR=/work/work/analysis/inetutils-2.8/translations/c2rust-0.22.1/cargo-target
    python3 /work/scripts/check_cargo_crate.py \
      --crate "$crate" --output "$crate/rustbox-cargo-check.json"
    cd "$crate"
    cargo build --release
  '
