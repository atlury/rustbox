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
canonical_build=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("canonical_build", "canonical-clang-compdb"))' "$manifest")
case $canonical_build in
  *[!A-Za-z0-9_-]*|'') echo "unsafe canonical build name" >&2; exit 2 ;;
esac
exec "$root/scripts/run_tool.sh" python3 /work/tests/coreutils_batch_valgrind.py \
  --canonical "/rustbox-coreutils/$canonical_build/src/coreutils" \
  --binary "/rustbox-coreutils/$canonical_build/src/coreutils-rust-$batch" \
  --manifest "/work/batches/$batch.json" \
  --output "/work/work/analysis/coreutils-9.12/translations/c2rust-0.22.1/$batch-stable/valgrind.json"
