#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

usage() {
  echo "usage: $0 BATCH audit|reachable [canonical|normalized]" >&2
  exit 2
}

test "$#" -ge 2 && test "$#" -le 3 || usage
batch=$1
mode=$2
variant=${3:-canonical}
case $batch in
  *[!A-Za-z0-9_-]*|'') usage ;;
esac
case $mode in
  audit|reachable) ;;
  *) usage ;;
esac
case $variant in
  canonical|normalized) ;;
  *) usage ;;
esac

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
manifest="$root/batches/$batch.json"
analysis="$root/work/analysis/coreutils-9.12"
database="$analysis/canonical-clang/compile_commands.json"
slice="$analysis/slices/$batch/compile_commands.json"
slice_container="/work/work/analysis/coreutils-9.12/slices/$batch/compile_commands.json"
output_name="$batch-$mode"
if test "$variant" = normalized; then
  slice="$analysis/normalized/$batch/compile_commands.json"
  slice_container="/work/work/analysis/coreutils-9.12/normalized/$batch/compile_commands.json"
  output_name="$batch-normalized-$mode"
fi
output="$analysis/translations/c2rust-0.22.1/$output_name"

test -s "$manifest" || { echo "unknown batch: $batch" >&2; exit 2; }
test -s "$database" || {
  echo "run scripts/capture_coreutils_compdb.sh first" >&2
  exit 1
}

regex=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["output_regex"])' "$manifest")
expected=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["expected_compile_commands"])' "$manifest")
if test "$variant" = canonical; then
  "$root/scripts/extract_compdb_slice.py" \
    --database "$database" \
    --output "$slice" \
    --output-regex "$regex" \
    --expected-commands "$expected"
else
  test -s "$slice" || {
    echo "run scripts/normalize_coreutils_batch.sh $batch first" >&2
    exit 1
  }
fi
mkdir -p "$output"

set -- c2rust transpile \
  "$slice_container" \
  --output-dir "/work/work/analysis/coreutils-9.12/translations/c2rust-0.22.1/$output_name" \
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
