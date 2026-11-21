#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
analysis="$root/work/analysis/lz4-1.11.1"
output="$analysis/translations/c2rust-0.22.1/lz4-1.11.1-normalized-audit"
database=/rustbox-lz4/normalized-clang/compile_commands.json
selected=/work/work/analysis/lz4-1.11.1/normalized/c2rust-compdb/compile_commands.json

RUSTBOX_TOOL_IMAGE=rustbox-lz4:2026-11-21 \
  "$root/scripts/run_tool.sh" python3 /work/scripts/prepare_lz4_c2rust.py \
    --database "$database" --oracle /work/evidence/lz4-1.11.1-oracle.json \
    --output "$selected"

case "$output" in
  "$analysis/translations/c2rust-0.22.1/"*) test ! -e "$output" || rm -rf -- "$output" ;;
  *) exit 2 ;;
esac
mkdir -p "$output"

RUSTBOX_TOOL_IMAGE=rustbox-lz4:2026-11-21 \
  exec "$root/scripts/run_tool.sh" c2rust transpile \
    /work/work/analysis/lz4-1.11.1/normalized/c2rust-compdb/compile_commands.json \
    --output-dir /work/work/analysis/lz4-1.11.1/translations/c2rust-0.22.1/lz4-1.11.1-normalized-audit \
    --emit-build-files \
    --fail-on-error \
    --disable-rustfmt \
    --overwrite-existing \
    --preserve-unused-functions
