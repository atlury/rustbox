#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
directory=/work/work/analysis/tar-1.35/normalized/c2rust-probe
database=$directory/compile_commands.json
source=/rustbox-tar/c2rust-probe-source

RUSTBOX_TOOL_IMAGE=rustbox-tar:2026-11-22 \
  "$root/scripts/run_tool.sh" python3 /work/scripts/prepare_tar_c2rust.py \
    --database /rustbox-tar/normalized-clang/compile_commands.json \
    --oracle /work/evidence/tar-1.35-oracle.json \
    --output "$database" \
    --source-output "$source"

RUSTBOX_TOOL_IMAGE=rustbox-tar:2026-11-22 \
  exec "$root/scripts/run_tool.sh" python3 /work/scripts/probe_tar_c2rust.py \
    --database "$database" \
    --source-root "$source" \
    --normalization /work/work/analysis/tar-1.35/normalized/normalization.json \
    --output "$directory/results.json"
