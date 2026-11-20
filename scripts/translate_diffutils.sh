#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
analysis="$root/work/analysis/diffutils-3.12"
output="$analysis/translations/c2rust-0.22.1/diffutils-3.12-normalized-audit"
database=/rustbox-diffutils/normalized-clang/compile_commands.json
selected=/work/work/analysis/diffutils-3.12/normalized/c2rust-compdb/compile_commands.json

RUSTBOX_TOOL_IMAGE=rustbox-diffutils:2026-11-20 \
  "$root/scripts/run_tool.sh" python3 /work/scripts/prepare_diffutils_c2rust.py \
    --database "$database" --output "$selected"

case "$output" in
  "$analysis/translations/c2rust-0.22.1/"*)
    test ! -e "$output" || rm -rf -- "$output"
    ;;
  *) exit 2 ;;
esac
mkdir -p "$output"

RUSTBOX_TOOL_IMAGE=rustbox-diffutils:2026-11-20 \
  exec "$root/scripts/run_tool.sh" c2rust transpile \
    /work/work/analysis/diffutils-3.12/normalized/c2rust-compdb/compile_commands.json \
    --output-dir /work/work/analysis/diffutils-3.12/translations/c2rust-0.22.1/diffutils-3.12-normalized-audit \
    --emit-build-files \
    --emit-c-decl-map \
    --fail-on-error \
    --disable-rustfmt \
    --overwrite-existing \
    --preserve-unused-functions
