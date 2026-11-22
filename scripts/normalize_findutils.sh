#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
exec python3 "$root/scripts/normalize_findutils.py" \
  --repository "$root" \
  --output "$root/work/normalized/findutils-4.10.0" \
  --manifest "$root/work/analysis/findutils-4.10.0/normalization-manifest.json"
