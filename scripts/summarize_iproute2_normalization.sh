#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
exec python3 -B "$root/scripts/summarize_iproute2_normalization.py" \
  --repository "$root" \
  --output "$root/evidence/iproute2-7.3.0-normalization.json"
