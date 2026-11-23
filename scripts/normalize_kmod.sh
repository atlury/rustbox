#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
exec python3 -B "$root/scripts/normalize_kmod.py" \
  --repository "$root" \
  --output "$root/work/normalized/kmod-34.3" \
  --manifest "$root/work/analysis/kmod-34.3/normalization-manifest.json"
