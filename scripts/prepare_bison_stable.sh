#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
base="$root/work/analysis/bison-3.8.2/translations/c2rust-0.22.1"
input="$base/bison-3.8.2-normalized-audit"
linked="$base/bison-3.8.2-linked"
stable="$base/bison-3.8.2-stable"

python3 -B "$root/scripts/link_c2rust_cross_module_types.py" \
  --input "$input" --output "$linked"
python3 -B "$root/scripts/modernize_c2rust_output.py" \
  --input "$linked" --output "$stable"
python3 -B "$root/scripts/finalize_bison_stable.py" --crate "$stable"

RUSTBOX_TOOL_IMAGE=rustbox-bison:2026-11-23 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    crate=/work/work/analysis/bison-3.8.2/translations/c2rust-0.22.1/bison-3.8.2-stable
    python3 /work/scripts/check_cargo_crate.py \
      --crate "$crate" --output "$crate/rustbox-cargo-check.json"
    cd "$crate"
    cargo build --release
  '
