#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
analysis="$root/work/analysis/coreutils-9.12"
database="$analysis/canonical-clang/compile_commands.json"
slice="$analysis/slices/true-false/compile_commands.json"
output="$analysis/translations/c2rust-0.22.1/true-false-reachable"

test -s "$database" || {
  echo "run scripts/capture_coreutils_compdb.sh first" >&2
  exit 1
}
"$root/scripts/extract_compdb_slice.py" \
  --database "$database" \
  --output "$slice" \
  --output-regex '/src/libsinglebin_(true|false)_'
mkdir -p "$output"

RUSTBOX_TOOL_IMAGE=rustbox-normalize:2026-11-19 \
  exec "$root/scripts/run_tool.sh" c2rust transpile \
    /work/work/analysis/coreutils-9.12/slices/true-false/compile_commands.json \
    --output-dir /work/work/analysis/coreutils-9.12/translations/c2rust-0.22.1/true-false-reachable \
    --emit-build-files \
    --emit-c-decl-map \
    --fail-on-error \
    --disable-rustfmt \
    --overwrite-existing
