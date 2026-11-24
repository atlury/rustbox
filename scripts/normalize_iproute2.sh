#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
exec python3 -B "$root/scripts/normalize_iproute2.py" \
  --repository "$root" \
  --output "$root/work/normalized/iproute2-7.3.0"
