#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-procps:2026-11-24 \
  exec "$root/scripts/run_tool.sh" python3 -B \
    /work/scripts/summarize_procps_translation.py \
    --repository /work \
    --archive /work/work/analysis/procps-ng-4.0.7/translations/c2rust-0.22.1/procps-ng-4.0.7-nightly/target/release/libprocps_ng_4_0_7_normalized_audit.a \
    --hybrid /work/work/analysis/procps-ng-4.0.7/hybrid \
    --output /work/evidence/procps-ng-4.0.7-translation.json
