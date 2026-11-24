#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
exec docker run --rm --platform linux/amd64 \
  --volume "$root:/work" \
  --volume rustbox-e2fsprogs-1.47.4:/rustbox-e2fsprogs \
  --workdir /work rustbox-e2fsprogs:2026-11-24 \
  python3 -B /work/scripts/summarize_e2fsprogs_program_hybrids.py \
    --repository /work \
    --hybrid-root /rustbox-e2fsprogs/program-hybrids \
    --output /work/evidence/e2fsprogs-1.47.4-program-hybrids.json
