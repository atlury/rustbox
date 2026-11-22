#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
base="$root/work/analysis/ncurses-6.6/translations/c2rust-0.22.1"
raw="$base/ncurses-6.6-normalized-audit"
stable="$base/ncurses-6.6-normalized-audit-stable"
result="$root/work/analysis/ncurses-6.6/normalized/modernization-result.json"

python3 "$root/scripts/modernize_c2rust_output.py" \
  --input "$raw" \
  --output "$stable" >"$result"

RUSTBOX_TOOL_IMAGE=rustbox-tar:2026-11-22 \
  exec "$root/scripts/run_tool.sh" python3 /work/scripts/check_cargo_crate.py \
    --crate /work/work/analysis/ncurses-6.6/translations/c2rust-0.22.1/ncurses-6.6-normalized-audit-stable \
    --output /work/work/analysis/ncurses-6.6/translations/c2rust-0.22.1/ncurses-6.6-normalized-audit-stable/rustbox-cargo-check.json
