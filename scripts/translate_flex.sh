#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
analysis="$root/work/analysis/flex-2.6.4"
output="$analysis/translations/c2rust-0.22.1/flex-2.6.4-normalized-audit"
selected="$analysis/normalized/c2rust-compdb/compile_commands.json"

RUSTBOX_TOOL_IMAGE=rustbox-flex:2026-11-22 \
  "$root/scripts/run_tool.sh" python3 -B /work/scripts/prepare_flex_c2rust.py \
    --database /work/work/analysis/flex-2.6.4/normalized/clang-compile-commands.json \
    --normalization /work/work/analysis/flex-2.6.4/normalization-manifest.json \
    --output /work/work/analysis/flex-2.6.4/normalized/c2rust-compdb/compile_commands.json

case "$output" in
  "$analysis/translations/c2rust-0.22.1/"*) test ! -e "$output" || rm -rf -- "$output" ;;
  *) exit 2 ;;
esac
mkdir -p "$output"

RUSTBOX_TOOL_IMAGE=rustbox-flex:2026-11-22 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    RAYON_NUM_THREADS=1 c2rust transpile \
      /work/work/analysis/flex-2.6.4/normalized/c2rust-compdb/compile_commands.json \
      --output-dir /work/work/analysis/flex-2.6.4/translations/c2rust-0.22.1/flex-2.6.4-normalized-audit \
      --emit-build-files --fail-on-error --disable-rustfmt \
      --overwrite-existing --preserve-unused-functions
  '
