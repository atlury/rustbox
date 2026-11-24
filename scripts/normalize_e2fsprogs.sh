#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
exec python3 -B "$root/scripts/normalize_e2fsprogs.py" \
  --repository "$root" \
  --output "$root/work/normalized/e2fsprogs-1.47.4" \
  --manifest "$root/work/analysis/e2fsprogs-1.47.4/normalization/manifest.json"
