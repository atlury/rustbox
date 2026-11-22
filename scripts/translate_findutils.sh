#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
analysis="$root/work/analysis/findutils-4.10.0"
output="$analysis/translations/c2rust-0.22.1/findutils-4.10.0-normalized-audit"
selected=/work/work/analysis/findutils-4.10.0/normalized/c2rust-compdb/compile_commands.json

RUSTBOX_TOOL_IMAGE=rustbox-findutils:2026-11-22 \
  "$root/scripts/run_tool.sh" python3 /work/scripts/prepare_findutils_c2rust.py \
    --database /rustbox-findutils/normalized-clang/compile_commands.json \
    --normalization /work/work/analysis/findutils-4.10.0/normalization-manifest.json \
    --output "$selected"

case "$output" in
  "$analysis/translations/c2rust-0.22.1/"*) test ! -e "$output" || rm -rf -- "$output" ;;
  *) exit 2 ;;
esac
mkdir -p "$output"

RUSTBOX_TOOL_IMAGE=rustbox-findutils:2026-11-22 \
  exec "$root/scripts/run_tool.sh" c2rust transpile \
    "$selected" \
    --output-dir /work/work/analysis/findutils-4.10.0/translations/c2rust-0.22.1/findutils-4.10.0-normalized-audit \
    --emit-build-files \
    --emit-c-decl-map \
    --fail-on-error \
    --disable-rustfmt \
    --overwrite-existing \
    --preserve-unused-functions
