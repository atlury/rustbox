#!/bin/sh
# SPDX-License-Identifier: ISC
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-normalize:2026-11-19 \
  exec "$root/scripts/run_tool.sh" python3 /work/scripts/summarize_pkgconf_hybrid.py \
    --repository /work --output /work/evidence/pkgconf-3.0.11-hybrid.json
