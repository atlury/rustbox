#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
analysis="$root/work/analysis/less-710"
output="$analysis/translations/c2rust-0.22.1/less-710-normalized-audit"
database=/rustbox-less/normalized-clang/compile_commands.json
selected=/work/work/analysis/less-710/normalized/c2rust-compdb/compile_commands.json

RUSTBOX_TOOL_IMAGE=rustbox-less:2026-11-22 \
  "$root/scripts/run_tool.sh" python3 /work/scripts/prepare_less_c2rust.py \
    --database "$database" \
    --normalization /work/evidence/less-710-normalization.json \
    --output "$selected"

case "$output" in
  "$analysis/translations/c2rust-0.22.1/"*) test ! -e "$output" || rm -rf -- "$output" ;;
  *) exit 2 ;;
esac
mkdir -p "$output"

RUSTBOX_TOOL_IMAGE=rustbox-less:2026-11-22 \
  exec "$root/scripts/run_tool.sh" c2rust transpile \
    /work/work/analysis/less-710/normalized/c2rust-compdb/compile_commands.json \
    --output-dir /work/work/analysis/less-710/translations/c2rust-0.22.1/less-710-normalized-audit \
    --emit-build-files \
    --emit-c-decl-map \
    --fail-on-error \
    --disable-rustfmt \
    --overwrite-existing \
    --preserve-unused-functions
