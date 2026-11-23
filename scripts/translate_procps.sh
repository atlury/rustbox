#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
analysis="$root/work/analysis/procps-ng-4.0.7"
output="$analysis/translations/c2rust-0.22.1/procps-ng-4.0.7-normalized-audit"

RUSTBOX_TOOL_IMAGE=rustbox-procps:2026-11-24 \
  "$root/scripts/run_tool.sh" python3 -B /work/scripts/prepare_procps_c2rust.py \
    --database /work/work/analysis/procps-ng-4.0.7/normalized/clang-18-compile-commands.json \
    --oracle /work/evidence/procps-ng-4.0.7-oracle.json \
    --normalization /work/evidence/procps-ng-4.0.7-normalization.json \
    --output /work/work/analysis/procps-ng-4.0.7/normalized/c2rust-compdb/compile_commands.json

case "$output" in
  "$analysis/translations/c2rust-0.22.1/"*) test ! -e "$output" || rm -rf -- "$output" ;;
  *) exit 2 ;;
esac
mkdir -p "$output"

RUSTBOX_TOOL_IMAGE=rustbox-procps:2026-11-24 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    RAYON_NUM_THREADS=1 c2rust transpile \
      /work/work/analysis/procps-ng-4.0.7/normalized/c2rust-compdb/compile_commands.json \
      --output-dir /work/work/analysis/procps-ng-4.0.7/translations/c2rust-0.22.1/procps-ng-4.0.7-normalized-audit \
      --emit-build-files --fail-on-error --disable-rustfmt \
      --overwrite-existing --preserve-unused-functions
  '
