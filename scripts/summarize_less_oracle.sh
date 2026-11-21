#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-less:2026-11-22 \
  exec "$root/scripts/run_tool.sh" python3 /work/scripts/summarize_less_oracle.py \
    --repository /work --output /work/evidence/less-710-oracle.json
