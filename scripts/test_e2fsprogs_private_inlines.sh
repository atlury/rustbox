#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu
root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
name=${1:-badblocks}
case "$name" in *[!a-z0-9_]*|'') exit 2 ;; esac
test "$#" -le 1
source="$root/work/analysis/e2fsprogs-1.47.4/program-translations/$name/$name-final"
test -d "$source"
scratch=$(mktemp -d "$root/work/analysis/private-inlines.XXXXXXXX")
trap 'rm -rf "$scratch"' EXIT
check() {
    docker run --rm --network none --platform linux/amd64 \
        -v "$root:/work:ro" -v "$scratch:/measure" -v rustbox-e2fsprogs-1.47.4:/rustbox-e2fsprogs:ro \
        rustbox-e2fsprogs:2026-11-24 python3 -B /work/scripts/check_e2fsprogs_private_inlines.py \
        "$1" "$name" /measure
}
check lint
cargo run --quiet --release --locked --offline --target-dir "$root/work/analysis/private-inlines-tools" \
    --manifest-path "$root/tools/private-inlines/Cargo.toml" -- \
    "$source" "$scratch/rustc.jsonl" "$scratch/overlay"
check verify
