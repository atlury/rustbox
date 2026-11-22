#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
analysis="$root/work/analysis/zstd-1.5.7"
output="$analysis/translations/c2rust-0.22.1/zstd-1.5.7-normalized-audit"
selected=/work/work/analysis/zstd-1.5.7/normalized/c2rust-compdb/compile_commands.json
source_output=/work/work/analysis/zstd-1.5.7/normalized/c2rust-source

RUSTBOX_TOOL_IMAGE=rustbox-zstd:2026-11-22 \
  "$root/scripts/run_tool.sh" python3 /work/scripts/prepare_zstd_c2rust.py \
    --database /rustbox-zstd/normalized-clang/compile_commands.json \
    --normalization /work/evidence/zstd-1.5.7-normalization.json \
    --output "$selected" \
    --source-output "$source_output"

"$root/scripts/validate_zstd_translation_source.sh"

case "$output" in
  "$analysis/translations/c2rust-0.22.1/"*) test ! -e "$output" || rm -rf -- "$output" ;;
  *) exit 2 ;;
esac
mkdir -p "$output"

RUSTBOX_TOOL_IMAGE=rustbox-zstd:2026-11-22 \
  exec "$root/scripts/run_tool.sh" c2rust transpile \
    "$selected" \
    --output-dir /work/work/analysis/zstd-1.5.7/translations/c2rust-0.22.1/zstd-1.5.7-normalized-audit \
    --emit-build-files \
    --fail-on-error \
    --disable-rustfmt \
    --overwrite-existing \
    --preserve-unused-functions
