#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)

RUSTBOX_TOOL_IMAGE=rustbox-normalize:2026-11-19 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    crate=/work/work/analysis/m4-1.4.21/translations/c2rust-0.22.1/m4-1.4.21-normalized-audit
    RUSTUP_TOOLCHAIN=nightly-2023-04-15 \
      python3 /work/scripts/check_cargo_crate.py \
        --crate "$crate" --output "$crate/rustbox-cargo-check.json"
  '
