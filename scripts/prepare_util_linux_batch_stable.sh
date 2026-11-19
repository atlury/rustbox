#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

test "$#" -eq 1 || { echo "usage: $0 BATCH" >&2; exit 2; }
batch=$1
case $batch in *[!A-Za-z0-9_-]*|'') exit 2 ;; esac

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
base="$root/work/analysis/util-linux-2.42.4/translations/c2rust-0.22.1"
input="$batch-normalized-reachable-prepared"
test -s "$base/$input/Cargo.toml" || {
  echo "prepare and compile-check the reachable crate first" >&2
  exit 1
}
"$root/scripts/modernize_c2rust_output.py" \
  --input "$base/$input" \
  --output "$base/$batch-stable"

RUSTBOX_TOOL_IMAGE=rustbox-normalize:2026-11-19 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    python3 /work/scripts/check_cargo_crate.py \
      --crate "$1" \
      --output "$1/rustbox-cargo-check.json"
    cd "$1"
    cargo build --release
  ' rustbox-util-linux-stable \
    "/work/work/analysis/util-linux-2.42.4/translations/c2rust-0.22.1/$batch-stable"
