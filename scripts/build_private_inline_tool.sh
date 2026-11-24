#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu
root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
target="$root/work/analysis/private-inlines-linux"
mkdir -p "$target"
scratch=$(mktemp -d "$root/work/analysis/private-inlines-vendor.XXXXXXXX")
trap 'rm -rf "$scratch"' EXIT
# Keep Cargo build dependencies outside the final multicall and use the pinned lock.
cargo vendor --locked --offline --manifest-path "$root/tools/private-inlines/Cargo.toml" \
    "$scratch/crates" >/dev/null
docker run --rm --network none --platform linux/amd64 --workdir /work \
  -v "$root:/work:ro" -v "$scratch/crates:/vendor:ro" -v "$target:/target" \
  rustbox-e2fsprogs:2026-11-24 cargo build --locked --offline --release \
  --target-dir /target --manifest-path tools/private-inlines/Cargo.toml \
  --config 'source.crates-io.replace-with="local-vendor"' --config 'source.local-vendor.directory="/vendor"'
