#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

test "$#" -ge 2 && test "$#" -le 3 || {
  echo "usage: $0 BATCH audit|reachable [canonical|normalized]" >&2
  exit 2
}
batch=$1
mode=$2
variant=${3:-canonical}
case $batch in
  *[!A-Za-z0-9_-]*|'') exit 2 ;;
esac
case $mode in audit|reachable) ;; *) exit 2 ;; esac
case $variant in
  canonical) input="$batch-$mode" ;;
  normalized) input="$batch-normalized-$mode" ;;
  *) exit 2 ;;
esac

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
base="$root/work/analysis/coreutils-9.12/translations/c2rust-0.22.1"
"$root/scripts/prepare_c2rust_scaffold.py" \
  --input "$base/$input" \
  --output "$base/$input-prepared"

RUSTBOX_TOOL_IMAGE=rustbox-normalize:2026-11-19 \
  exec "$root/scripts/run_tool.sh" python3 /work/scripts/check_cargo_crate.py \
    --crate "/work/work/analysis/coreutils-9.12/translations/c2rust-0.22.1/$input-prepared" \
    --toolchain nightly-2023-04-15 \
    --output "/work/work/analysis/coreutils-9.12/translations/c2rust-0.22.1/$input-prepared/rustbox-cargo-check.json"
