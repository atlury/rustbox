#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
directory=/work/work/analysis/ncurses-6.6/normalized/c2rust-probe
database=$directory/compile_commands.json
source=/rustbox-ncurses/c2rust-probe-source

RUSTBOX_TOOL_IMAGE=rustbox-tar:2026-11-22 \
  "$root/scripts/run_tool.sh" python3 /work/scripts/prepare_ncurses_c2rust.py \
    --database /rustbox-ncurses/normalized-clang/compile_commands.json \
    --normalization /work/work/analysis/ncurses-6.6/normalization-manifest.json \
    --output "$database" \
    --source-output "$source"

RUSTBOX_TOOL_IMAGE=rustbox-tar:2026-11-22 \
  exec "$root/scripts/run_tool.sh" python3 /work/scripts/probe_ncurses_c2rust.py \
    --database "$database" \
    --source-root "$source" \
    --normalization /work/work/analysis/ncurses-6.6/normalization-manifest.json \
    --output "$directory/results.json"
