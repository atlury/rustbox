#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
exec python3 -B "$root/scripts/normalize_procps.py" \
  --repository "$root" \
  --output "$root/work/normalized/procps-ng-4.0.7"
