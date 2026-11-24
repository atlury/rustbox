#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-shadow:2026-11-24 \
  exec "$root/scripts/run_tool.sh" python3 -B \
    /work/scripts/summarize_shadow_translation.py \
    --repository /work \
    --archive /work/work/analysis/shadow-4.20.4/translations/c2rust-0.22.1/shadow-4.20.4-nightly/target/release/libshadow_4_20_4_normalized_audit.a \
    --hybrid /work/work/analysis/shadow-4.20.4/hybrid \
    --output /work/evidence/shadow-4.20.4-c2rust.json
