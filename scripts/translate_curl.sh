#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
analysis="$root/work/analysis/curl-8.23.0"
output="$analysis/translations/c2rust-0.22.1/curl-8.23.0-normalized-audit"
selected="$analysis/normalized/c2rust-compdb/compile_commands.json"

RUSTBOX_TOOL_IMAGE=rustbox-curl:2026-11-23 \
  "$root/scripts/run_tool.sh" python3 -B /work/scripts/prepare_curl_c2rust.py \
    --database /work/work/analysis/curl-8.23.0/normalized/clang-compile-commands.json \
    --normalization /work/work/analysis/curl-8.23.0/normalization-manifest.json \
    --oracle /work/evidence/curl-8.23.0-oracle.json \
    --output /work/work/analysis/curl-8.23.0/normalized/c2rust-compdb/compile_commands.json \
    --source-output /work/work/analysis/curl-8.23.0/normalized/c2rust-source

case "$output" in
  "$analysis/translations/c2rust-0.22.1/"*) test ! -e "$output" || rm -rf -- "$output" ;;
  *) exit 2 ;;
esac
mkdir -p "$output"

RUSTBOX_TOOL_IMAGE=rustbox-curl:2026-11-23 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    RAYON_NUM_THREADS=1 c2rust transpile \
      /work/work/analysis/curl-8.23.0/normalized/c2rust-compdb/compile_commands.json \
      --output-dir /work/work/analysis/curl-8.23.0/translations/c2rust-0.22.1/curl-8.23.0-normalized-audit \
      --emit-build-files --fail-on-error --disable-rustfmt \
      --overwrite-existing --preserve-unused-functions
  '
