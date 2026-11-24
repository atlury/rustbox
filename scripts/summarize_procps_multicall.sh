#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
exec python3 -B "$root/scripts/summarize_procps_multicall.py" \
  --repository "$root" \
  --output "$root/evidence/procps-ng-4.0.7-multicall.json"
