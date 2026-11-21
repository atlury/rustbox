#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
analysis="$root/work/analysis/gzip-1.14"
output="$analysis/translations/c2rust-0.22.1/gzip-1.14-normalized-audit"
database=/rustbox-gzip/normalized-clang/compile_commands.json
selected=/work/work/analysis/gzip-1.14/normalized/c2rust-compdb/compile_commands.json

RUSTBOX_TOOL_IMAGE=rustbox-gzip:2026-11-21 \
  "$root/scripts/run_tool.sh" python3 /work/scripts/prepare_gzip_c2rust.py \
    --database "$database" \
    --normalization /work/evidence/gzip-1.14-normalization.json \
    --output "$selected"

case "$output" in
  "$analysis/translations/c2rust-0.22.1/"*) test ! -e "$output" || rm -rf -- "$output" ;;
  *) exit 2 ;;
esac
mkdir -p "$output"

RUSTBOX_TOOL_IMAGE=rustbox-gzip:2026-11-21 \
  exec "$root/scripts/run_tool.sh" c2rust transpile \
    /work/work/analysis/gzip-1.14/normalized/c2rust-compdb/compile_commands.json \
    --output-dir /work/work/analysis/gzip-1.14/translations/c2rust-0.22.1/gzip-1.14-normalized-audit \
    --emit-build-files \
    --fail-on-error \
    --disable-rustfmt \
    --overwrite-existing \
    --preserve-unused-functions
