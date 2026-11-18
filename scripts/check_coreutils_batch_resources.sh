#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

test "$#" -eq 1 || { echo "usage: $0 BATCH" >&2; exit 2; }
batch=$1
case $batch in
  *[!A-Za-z0-9_-]*|'') exit 2 ;;
esac

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
manifest="$root/batches/$batch.json"
test -s "$manifest" || { echo "unknown batch: $batch" >&2; exit 2; }
exec "$root/scripts/run_tool.sh" python3 /work/tests/coreutils_batch_valgrind.py \
  --binary "/rustbox-coreutils/canonical-clang-compdb/src/coreutils-rust-$batch" \
  --manifest "/work/batches/$batch.json" \
  --output "/work/work/analysis/coreutils-9.12/translations/c2rust-0.22.1/$batch-stable/valgrind.json"
