#!/bin/sh
# SPDX-License-Identifier: BSD-2-Clause
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
analysis="$root/work/analysis/file-5.48"
output="$analysis/translations/c2rust-0.22.1/file-5.48-normalized-audit"

RUSTBOX_TOOL_IMAGE=rustbox-file:2026-11-20 \
  "$root/scripts/run_tool.sh" python3 /work/scripts/prepare_file_c2rust.py \
    --database /rustbox-file/normalized-clang/compile_commands.json \
    --output /work/work/analysis/file-5.48/normalized/c2rust-compdb/compile_commands.json

case "$output" in
  "$analysis/translations/c2rust-0.22.1/"*)
    test ! -e "$output" || rm -rf -- "$output"
    ;;
  *) exit 2 ;;
esac
mkdir -p "$output"

RUSTBOX_TOOL_IMAGE=rustbox-file:2026-11-20 \
  exec "$root/scripts/run_tool.sh" python3 /work/scripts/run_file_c2rust.py \
    --database /work/work/analysis/file-5.48/normalized/c2rust-compdb/compile_commands.json \
    --output /work/work/analysis/file-5.48/translations/c2rust-0.22.1/file-5.48-normalized-audit
