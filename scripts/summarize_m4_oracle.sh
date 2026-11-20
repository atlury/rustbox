#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
exec "$root/scripts/run_tool.sh" python3 /work/scripts/summarize_m4_oracle.py \
  --repository /work --output /work/evidence/m4-1.4.21-oracle.json
