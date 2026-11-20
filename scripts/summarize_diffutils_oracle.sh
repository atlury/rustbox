#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-diffutils:2026-11-20 \
  exec "$root/scripts/run_tool.sh" python3 /work/scripts/summarize_diffutils_oracle.py \
    --repository /work --output /work/evidence/diffutils-3.12-oracle.json
