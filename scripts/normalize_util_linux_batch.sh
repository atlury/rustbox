#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

test "$#" -eq 1 || { echo "usage: $0 BATCH" >&2; exit 2; }
batch=$1
case $batch in *[!A-Za-z0-9_-]*|'') exit 2 ;; esac

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
analysis="$root/work/analysis/util-linux-2.42.4"
slice="$analysis/slices/$batch/compile_commands.json"
gcc_database="$analysis/canonical-gcc/compile_commands.json"
gcc_slice="$analysis/slices/$batch/compile_commands-gcc.json"
manifest="$root/batches/$batch.json"
test -s "$slice" || { echo "extract or translate $batch first" >&2; exit 1; }
test -s "$gcc_database" || { echo "capture the GCC database first" >&2; exit 1; }
test -s "$manifest" || { echo "unknown batch: $batch" >&2; exit 2; }

regex=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["output_regex"])' "$manifest")
expected=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["expected_compile_commands"])' "$manifest")
"$root/scripts/extract_compdb_slice.py" \
  --database "$gcc_database" \
  --output "$gcc_slice" \
  --output-regex "$regex" \
  --expected-commands "$expected" \
  --require-unique-sources

RUSTBOX_TOOL_IMAGE=rustbox-normalize:2026-11-19 \
  exec "$root/scripts/run_tool.sh" python3 /work/scripts/normalize_coreutils_batch.py \
    --repository /work \
    --source-root /rustbox-util-linux-source/util-linux-2.42.4 \
    --database "/work/work/analysis/util-linux-2.42.4/slices/$batch/compile_commands.json" \
    --gcc-database "/work/work/analysis/util-linux-2.42.4/slices/$batch/compile_commands-gcc.json" \
    --manifest "/work/batches/$batch.json" \
    --output "/work/work/analysis/util-linux-2.42.4/normalized/$batch"
