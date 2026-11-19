#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

test "$#" -eq 2 || { echo "usage: $0 BATCH audit|reachable" >&2; exit 2; }
batch=$1
mode=$2
case $batch in *[!A-Za-z0-9_-]*|'') exit 2 ;; esac
case $mode in audit|reachable) ;; *) exit 2 ;; esac

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
base="$root/work/analysis/util-linux-2.42.4/translations/c2rust-0.22.1"
input="$batch-normalized-$mode"
"$root/scripts/prepare_c2rust_scaffold.py" \
  --input "$base/$input" \
  --output "$base/$input-prepared"

RUSTBOX_TOOL_IMAGE=rustbox-normalize:2026-11-19 \
  exec "$root/scripts/run_tool.sh" python3 /work/scripts/check_cargo_crate.py \
    --crate "/work/work/analysis/util-linux-2.42.4/translations/c2rust-0.22.1/$input-prepared" \
    --toolchain nightly-2023-04-15 \
    --output "/work/work/analysis/util-linux-2.42.4/translations/c2rust-0.22.1/$input-prepared/rustbox-cargo-check.json"
