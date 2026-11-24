#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu
root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
# The pinned ss lock contains the registry packages used by the IPRoute2 engines.
exec docker run --rm --platform linux/amd64 -v "$root:/work:ro" \
    -v rustbox-pointer-cargo-registry:/root/.cargo/registry \
    --workdir /work/work/analysis/iproute2-7.3.0/program-translations/ss/ss-final \
    rustbox-e2fsprogs:2026-11-24 cargo fetch --locked
