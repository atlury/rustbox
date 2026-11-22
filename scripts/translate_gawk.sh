#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
analysis="$root/work/analysis/gawk-5.4.0"
output="$analysis/translations/c2rust-0.22.1/gawk-5.4.0-normalized-audit"
selected=/work/work/analysis/gawk-5.4.0/normalized/c2rust-compdb/compile_commands.json
batches=/work/work/analysis/gawk-5.4.0/normalized/c2rust-compdb-batches

RUSTBOX_TOOL_IMAGE=rustbox-gawk:2026-11-22 \
  "$root/scripts/run_tool.sh" python3 /work/scripts/prepare_gawk_c2rust.py \
    --database /rustbox-gawk/normalized-clang/compile_commands.json \
    --normalization /work/work/analysis/gawk-5.4.0/normalization-manifest.json \
    --output "$selected"
RUSTBOX_TOOL_IMAGE=rustbox-gawk:2026-11-22 \
  "$root/scripts/run_tool.sh" python3 /work/scripts/batch_gawk_c2rust.py \
    --database "$selected" --output-dir "$batches"

case "$output" in
  "$analysis/translations/c2rust-0.22.1/"*) test ! -e "$output" || rm -rf -- "$output" ;;
  *) exit 2 ;;
esac
mkdir -p "$output"

RUSTBOX_TOOL_IMAGE=rustbox-gawk:2026-11-22 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    for database in /work/work/analysis/gawk-5.4.0/normalized/c2rust-compdb-batches/batch-*/compile_commands.json; do
      batch=$(basename "$(dirname "$database")")
      destination=/work/work/analysis/gawk-5.4.0/translations/c2rust-0.22.1/gawk-5.4.0-normalized-audit/$batch
      mkdir -p "$destination"
      declaration_map=--emit-c-decl-map
      if grep -Eq "/(awkgram|command)\.c" "$database"; then
        declaration_map=
      fi
      RAYON_NUM_THREADS=1 c2rust transpile \
        "$database" --output-dir "$destination" --emit-build-files \
        $declaration_map --fail-on-error --disable-rustfmt \
        --overwrite-existing --preserve-unused-functions
    done
  '
