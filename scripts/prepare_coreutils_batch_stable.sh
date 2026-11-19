#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

test "$#" -ge 1 && test "$#" -le 2 || {
  echo "usage: $0 BATCH [canonical|normalized]" >&2
  exit 2
}
batch=$1
variant=${2:-canonical}
case $batch in
  *[!A-Za-z0-9_-]*|'') exit 2 ;;
esac
case $variant in
  canonical) input="$batch-reachable" ;;
  normalized) input="$batch-normalized-reachable" ;;
  *) exit 2 ;;
esac

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
base="$root/work/analysis/coreutils-9.12/translations/c2rust-0.22.1"
if test -s "$base/$input-prepared/Cargo.toml"; then
  input="$input-prepared"
fi
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
  ' rustbox-c2rust-stable \
    "/work/work/analysis/coreutils-9.12/translations/c2rust-0.22.1/$batch-stable"
