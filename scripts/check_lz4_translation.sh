#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-lz4:2026-11-21 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    crate=/work/work/analysis/lz4-1.11.1/translations/c2rust-0.22.1/lz4-1.11.1-normalized-audit
    RUSTUP_TOOLCHAIN=nightly-2023-04-15 \
      RUSTFLAGS="-Zcrate-attr=feature(c_variadic)" \
      python3 /work/scripts/check_cargo_crate.py \
        --crate "$crate" --output "$crate/rustbox-cargo-check.json"
  '
