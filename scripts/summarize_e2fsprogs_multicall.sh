#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
exec docker run --rm --platform linux/amd64 \
  --volume "$root:/work" \
  --volume rustbox-coreutils-9.12:/rustbox-coreutils \
  --workdir /work rustbox-e2fsprogs:2026-11-24 \
  python3 -B /work/scripts/summarize_e2fsprogs_multicall.py \
    --binary /rustbox-coreutils/canonical-clang-no-security-compdb/src/rustbox \
    --link-report /work/work/analysis/rustbox-multicall-link.json \
    --report-directory /work/work/analysis/e2fsprogs-1.47.4/multicall \
    --output /work/evidence/e2fsprogs-1.47.4-multicall.json
