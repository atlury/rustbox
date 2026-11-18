#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

test "$#" -eq 2 || {
  echo "usage: $0 BATCH audit|reachable" >&2
  exit 2
}
batch=$1
mode=$2
case $batch in
  *[!A-Za-z0-9_-]*|'') exit 2 ;;
esac
case $mode in
  audit|reachable) ;;
  *) exit 2 ;;
esac

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
host_output="$root/work/analysis/coreutils-9.12/translations/c2rust-0.22.1/$batch-$mode"
container_output="/work/work/analysis/coreutils-9.12/translations/c2rust-0.22.1/$batch-$mode"
test -s "$host_output/Cargo.toml" || {
  echo "run scripts/translate_coreutils_batch.sh $batch $mode first" >&2
  exit 1
}

RUSTBOX_TOOL_IMAGE=rustbox-normalize:2026-11-19 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    cd "$1"
    RUSTUP_TOOLCHAIN=nightly-2023-04-15 cargo check
  ' rustbox-c2rust-check "$container_output"
