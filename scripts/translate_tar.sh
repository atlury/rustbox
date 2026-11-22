#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
analysis="$root/work/analysis/tar-1.35"
output="$analysis/translations/c2rust-0.22.1/tar-1.35-normalized-audit"
selected=/work/work/analysis/tar-1.35/normalized/c2rust-compdb/compile_commands.json

RUSTBOX_TOOL_IMAGE=rustbox-tar:2026-11-22 \
  "$root/scripts/run_tool.sh" python3 /work/scripts/prepare_tar_c2rust.py \
    --database /rustbox-tar/normalized-clang/compile_commands.json \
    --oracle /work/evidence/tar-1.35-oracle.json \
    --output "$selected" \
    --source-output /rustbox-tar/c2rust-source

case "$output" in
  "$analysis/translations/c2rust-0.22.1/"*) test ! -e "$output" || rm -rf -- "$output" ;;
  *) exit 2 ;;
esac
mkdir -p "$output"

RUSTBOX_TOOL_IMAGE=rustbox-tar:2026-11-22 \
  exec "$root/scripts/run_tool.sh" c2rust transpile \
    "$selected" \
    --output-dir /work/work/analysis/tar-1.35/translations/c2rust-0.22.1/tar-1.35-normalized-audit \
    --emit-build-files \
    --fail-on-error \
    --disable-rustfmt \
    --overwrite-existing \
    --preserve-unused-functions
