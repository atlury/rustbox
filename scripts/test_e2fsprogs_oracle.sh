#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
exec docker run --rm --platform linux/amd64 \
  --volume "$root:/work" \
  --volume rustbox-e2fsprogs-1.47.4:/rustbox-e2fsprogs \
  --workdir /work rustbox-e2fsprogs:2026-11-24 \
  python3 -B /work/tests/e2fsprogs-oracle-differential.py \
    --gcc-root /rustbox-e2fsprogs/stage-gcc \
    --clang-root /rustbox-e2fsprogs/stage-clang-18 \
    --inventory /work/work/analysis/e2fsprogs-1.47.4/oracle/gcc-installed-executables.txt \
    --output /work/work/analysis/e2fsprogs-1.47.4/oracle/differential.json
