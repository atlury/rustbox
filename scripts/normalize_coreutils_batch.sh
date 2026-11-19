#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

test "$#" -eq 1 || { echo "usage: $0 BATCH" >&2; exit 2; }
batch=$1
case $batch in
  *[!A-Za-z0-9_-]*|'') exit 2 ;;
esac

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
slice="$root/work/analysis/coreutils-9.12/slices/$batch/compile_commands.json"
manifest="$root/batches/$batch.json"
test -s "$slice" || { echo "translate or extract $batch first" >&2; exit 1; }
test -s "$manifest" || { echo "unknown batch: $batch" >&2; exit 2; }
gcc_database="$root/work/analysis/coreutils-9.12/canonical-gcc/compile_commands.json"
test -s "$gcc_database" || {
  echo "run scripts/capture_coreutils_gcc_compdb.sh first" >&2
  exit 1
}

RUSTBOX_TOOL_IMAGE=rustbox-normalize:2026-11-19 \
  exec "$root/scripts/run_tool.sh" python3 /work/scripts/normalize_coreutils_batch.py \
    --repository /work \
    --source-root /rustbox-source/coreutils-9.12 \
    --database "/work/work/analysis/coreutils-9.12/slices/$batch/compile_commands.json" \
    --gcc-database /work/work/analysis/coreutils-9.12/canonical-gcc/compile_commands.json \
    --manifest "/work/batches/$batch.json" \
    --output "/work/work/analysis/coreutils-9.12/normalized/$batch"
