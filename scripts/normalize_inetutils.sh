#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
exec python3 "$root/scripts/normalize_inetutils.py" \
  --repository "$root" \
  --output "$root/work/normalized/inetutils-2.8" \
  --manifest "$root/work/analysis/inetutils-2.8/normalization-manifest.json"
