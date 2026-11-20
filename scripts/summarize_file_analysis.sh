#!/bin/sh
# SPDX-License-Identifier: BSD-2-Clause
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
exec python3 "$root/scripts/summarize_file_analysis.py" \
  --repository "$root" --output "$root/evidence/file-5.48-static-analysis.json"
