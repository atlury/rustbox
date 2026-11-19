#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
crate=/work/work/analysis/zlib-1.4/translations/c2rust-0.22.1/zlib-1.4-normalized-audit
RUSTBOX_TOOL_IMAGE=rustbox-normalize:2026-11-19 \
  exec "$root/scripts/run_tool.sh" python3 /work/scripts/check_cargo_crate.py \
    --crate "$crate" \
    --toolchain nightly-2023-04-15 \
    --output "$crate/rustbox-cargo-check.json"
