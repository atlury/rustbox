#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-acl:2026-11-21 \
  exec "$root/scripts/run_tool.sh" python3 /work/scripts/normalize_acl.py \
    --repository /work \
    --output /rustbox-acl/normalized-source \
    --manifest /work/work/analysis/acl-2.4.0/normalized/normalization.json
