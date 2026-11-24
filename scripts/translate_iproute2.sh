#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
analysis="$root/work/analysis/iproute2-7.3.0"
output="$analysis/translations/c2rust-0.22.1/iproute2-7.3.0-normalized-audit"

RUSTBOX_TOOL_IMAGE=rustbox-iproute2:2026-11-24 \
  "$root/scripts/run_tool.sh" python3 -B /work/scripts/prepare_iproute2_c2rust.py \
    --database /work/work/analysis/iproute2-7.3.0/normalized/clang-18-compile-commands.json \
    --oracle /work/evidence/iproute2-7.3.0-oracle.json \
    --normalization /work/evidence/iproute2-7.3.0-normalization.json \
    --output /work/work/analysis/iproute2-7.3.0/c2rust-compdb/compile_commands.json

case "$output" in
  "$analysis/translations/c2rust-0.22.1/"*) test ! -e "$output" || rm -rf -- "$output" ;;
  *) exit 2 ;;
esac
mkdir -p "$output"

RUSTBOX_TOOL_IMAGE=rustbox-iproute2:2026-11-24 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    RAYON_NUM_THREADS=1 c2rust transpile \
      /work/work/analysis/iproute2-7.3.0/c2rust-compdb/compile_commands.json \
      --output-dir /work/work/analysis/iproute2-7.3.0/translations/c2rust-0.22.1/iproute2-7.3.0-normalized-audit \
      --emit-build-files --fail-on-error --disable-rustfmt \
      --overwrite-existing --preserve-unused-functions
  '
