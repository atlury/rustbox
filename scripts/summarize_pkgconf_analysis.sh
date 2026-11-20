#!/bin/sh
# SPDX-License-Identifier: ISC
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
exec python3 "$root/scripts/summarize_pkgconf_analysis.py" \
  --repository "$root" --output "$root/evidence/pkgconf-3.0.11-static-analysis.json"
