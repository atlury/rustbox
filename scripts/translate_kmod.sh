#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
analysis="$root/work/analysis/kmod-34.3"
output="$analysis/translations/c2rust-0.22.1/kmod-34.3-normalized-audit"

RUSTBOX_TOOL_IMAGE=rustbox-kmod:2026-11-24 \
  "$root/scripts/run_tool.sh" python3 -B /work/scripts/prepare_kmod_c2rust.py \
    --database /work/work/analysis/kmod-34.3/normalized/clang-compile-commands.json \
    --normalization /work/work/analysis/kmod-34.3/normalization-manifest.json \
    --oracle /work/evidence/kmod-34.3-oracle.json \
    --output /work/work/analysis/kmod-34.3/normalized/c2rust-compdb/compile_commands.json

case "$output" in
  "$analysis/translations/c2rust-0.22.1/"*) test ! -e "$output" || rm -rf -- "$output" ;;
  *) exit 2 ;;
esac
mkdir -p "$output"

RUSTBOX_TOOL_IMAGE=rustbox-kmod:2026-11-24 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    RAYON_NUM_THREADS=1 c2rust transpile \
      /work/work/analysis/kmod-34.3/normalized/c2rust-compdb/compile_commands.json \
      --output-dir /work/work/analysis/kmod-34.3/translations/c2rust-0.22.1/kmod-34.3-normalized-audit \
      --emit-build-files --fail-on-error --disable-rustfmt \
      --overwrite-existing --preserve-unused-functions
  '
