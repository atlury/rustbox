#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-kmod:2026-11-24 \
  exec "$root/scripts/run_tool.sh" python3 -B /work/scripts/summarize_kmod_translation.py \
    --repository /work \
    --archive /work/work/analysis/kmod-34.3/translations/c2rust-0.22.1/kmod-34.3-stable/target/release/libkmod_34_3_normalized_audit.a \
    --output /work/evidence/kmod-34.3-c2rust.json
