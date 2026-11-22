#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-gawk:2026-11-22 \
  exec "$root/scripts/run_tool.sh" python3 /work/scripts/test_rustbox_batch_differential.py \
    --repository /work \
    --coreutils-root /rustbox-coreutils \
    --util-linux-build /rustbox-util-linux/canonical-clang-compdb \
    --rustbox /rustbox-coreutils/canonical-clang-no-security-compdb/src/rustbox \
    --report-directory /work/work/analysis/rustbox-multicall-differential \
    --jobs 4 --reuse-passing \
    --output /work/work/analysis/rustbox-multicall-differential.json
