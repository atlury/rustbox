#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

usage() {
  echo "usage: $0 BATCH audit|reachable" >&2
  exit 2
}

test "$#" -eq 2 || usage
batch=$1
mode=$2
case $batch in
  *[!A-Za-z0-9_-]*|'') usage ;;
esac
case $mode in
  audit|reachable) ;;
  *) usage ;;
esac

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
manifest="$root/batches/$batch.json"
analysis="$root/work/analysis/coreutils-9.12"
database="$analysis/canonical-clang/compile_commands.json"
slice="$analysis/slices/$batch/compile_commands.json"
output="$analysis/translations/c2rust-0.22.1/$batch-$mode"

test -s "$manifest" || { echo "unknown batch: $batch" >&2; exit 2; }
test -s "$database" || {
  echo "run scripts/capture_coreutils_compdb.sh first" >&2
  exit 1
}

regex=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["output_regex"])' "$manifest")
expected=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["expected_compile_commands"])' "$manifest")
"$root/scripts/extract_compdb_slice.py" \
  --database "$database" \
  --output "$slice" \
  --output-regex "$regex" \
  --expected-commands "$expected"
mkdir -p "$output"

set -- c2rust transpile \
  "/work/work/analysis/coreutils-9.12/slices/$batch/compile_commands.json" \
  --output-dir "/work/work/analysis/coreutils-9.12/translations/c2rust-0.22.1/$batch-$mode" \
  --emit-build-files \
  --emit-c-decl-map \
  --fail-on-error \
  --disable-rustfmt \
  --overwrite-existing
if test "$mode" = audit; then
  set -- "$@" --preserve-unused-functions
fi

RUSTBOX_TOOL_IMAGE=rustbox-normalize:2026-11-19 \
  exec "$root/scripts/run_tool.sh" "$@"
