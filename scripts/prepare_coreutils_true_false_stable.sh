#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
base="$root/work/analysis/coreutils-9.12/translations/c2rust-0.22.1"
"$root/scripts/modernize_c2rust_output.py" \
  --input "$base/true-false-reachable" \
  --output "$base/true-false-stable"
RUSTBOX_TOOL_IMAGE=rustbox-normalize:2026-11-19 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    cd /work/work/analysis/coreutils-9.12/translations/c2rust-0.22.1/true-false-stable
    cargo check
    cargo build --release
  '
