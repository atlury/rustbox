#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
exec docker run --rm --platform linux/amd64 \
  --volume "$root:/work" \
  --volume rustbox-e2fsprogs-1.47.4:/rustbox-e2fsprogs \
  --workdir /work --entrypoint sh rustbox-e2fsprogs:2026-11-24 -eu -c '
    base=/work/work/analysis/e2fsprogs-1.47.4/program-closures
    python3 -B /work/scripts/summarize_e2fsprogs_program_closures.py \
      --normalization-manifest "/work/work/analysis/e2fsprogs-1.47.4/normalization/manifest.json" \
      --maps-directory "$base/maps" \
      --engines-directory "$base/engines" \
      --output "$base/summary.json"
    chmod a+rw "$base/summary.json"
  '
