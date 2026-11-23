#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
base="$root/work/analysis/procps-ng-4.0.7/translations/c2rust-0.22.1"
audit="$base/procps-ng-4.0.7-normalized-audit"
nightly="$base/procps-ng-4.0.7-nightly"

python3 -B "$root/scripts/finalize_procps_nightly.py" \
  --input "$audit" --output "$nightly"

RUSTBOX_TOOL_IMAGE=rustbox-procps:2026-11-24 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    crate=/work/work/analysis/procps-ng-4.0.7/translations/c2rust-0.22.1/procps-ng-4.0.7-nightly
    python3 /work/scripts/check_cargo_crate.py \
      --crate "$crate" --output "$crate/rustbox-cargo-check.json" \
      --toolchain nightly-2023-04-15
    cd "$crate"
    RUSTUP_TOOLCHAIN=nightly-2023-04-15 cargo build --release
  '
