#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
exec docker run --rm --platform linux/amd64 \
  --volume "$root:/work" \
  --volume rustbox-e2fsprogs-1.47.4:/rustbox-e2fsprogs \
  --workdir /work rustbox-e2fsprogs:2026-11-24 sh -eu -c '
    evidence=/work/work/analysis/e2fsprogs-1.47.4/normalization
    inventory=$evidence/gcc-installed-executables.txt
    python3 -B /work/tests/e2fsprogs-oracle-differential.py \
      --gcc-root /rustbox-e2fsprogs/stage-gcc \
      --clang-root /rustbox-e2fsprogs/stage-normalized-gcc \
      --inventory "$inventory" \
      --output "$evidence/gcc-canonical-differential.json"
    python3 -B /work/tests/e2fsprogs-oracle-differential.py \
      --gcc-root /rustbox-e2fsprogs/stage-clang-18 \
      --clang-root /rustbox-e2fsprogs/stage-normalized-clang-18 \
      --inventory "$inventory" \
      --output "$evidence/clang-18-canonical-differential.json"
    python3 -B /work/tests/e2fsprogs-oracle-differential.py \
      --gcc-root /rustbox-e2fsprogs/stage-normalized-gcc \
      --clang-root /rustbox-e2fsprogs/stage-normalized-clang-18 \
      --inventory "$inventory" \
      --output "$evidence/compiler-differential.json"
    chmod -R a+rwX "$evidence"
  '
