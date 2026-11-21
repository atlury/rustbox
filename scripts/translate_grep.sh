#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
analysis="$root/work/analysis/grep-3.12"
output="$analysis/translations/c2rust-0.22.1/grep-3.12-normalized-audit"
database=/rustbox-grep/normalized-clang/compile_commands.json
selected=/work/work/analysis/grep-3.12/normalized/c2rust-compdb/compile_commands.json

RUSTBOX_TOOL_IMAGE=rustbox-grep:2026-11-21 \
  "$root/scripts/run_tool.sh" python3 /work/scripts/prepare_grep_c2rust.py \
    --database "$database" --output "$selected"

case "$output" in
  "$analysis/translations/c2rust-0.22.1/"*)
    test ! -e "$output" || rm -rf -- "$output"
    ;;
  *) exit 2 ;;
esac
mkdir -p "$output"

RUSTBOX_TOOL_IMAGE=rustbox-grep:2026-11-21 \
  exec "$root/scripts/run_tool.sh" c2rust transpile \
    /work/work/analysis/grep-3.12/normalized/c2rust-compdb/compile_commands.json \
    --output-dir /work/work/analysis/grep-3.12/translations/c2rust-0.22.1/grep-3.12-normalized-audit \
    --emit-build-files \
    --emit-c-decl-map \
    --fail-on-error \
    --disable-rustfmt \
    --overwrite-existing \
    --preserve-unused-functions
