#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

test "$#" -eq 1 || {
  echo "usage: $0 BATCH" >&2
  exit 2
}
batch=$1
case $batch in
  *[!A-Za-z0-9_-]*|'') exit 2 ;;
esac

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
manifest="$root/batches/$batch.json"
host_translation="$root/work/analysis/coreutils-9.12/translations/c2rust-0.22.1/$batch-stable"
container_translation="/work/work/analysis/coreutils-9.12/translations/c2rust-0.22.1/$batch-stable"
test -s "$manifest" || { echo "unknown batch: $batch" >&2; exit 2; }
library=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["reachable_staticlib"])' "$manifest")
test -s "$host_translation/target/release/$library" || {
  echo "run scripts/prepare_coreutils_batch_stable.sh $batch first" >&2
  exit 1
}

RUSTBOX_TOOL_IMAGE=rustbox-normalize:2026-11-19 \
  exec "$root/scripts/run_tool.sh" python3 \
    /work/scripts/link_coreutils_batch_hybrid.py \
    --build /rustbox-coreutils/canonical-clang-compdb \
    --rust-library "$container_translation/target/release/$library" \
    --manifest "/work/batches/$batch.json"
