#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-acl:2026-11-21 \
  exec "$root/scripts/run_tool.sh" python3 /work/scripts/summarize_acl_normalization.py \
    --repository /work --output /work/evidence/acl-2.4.0-normalization.json
