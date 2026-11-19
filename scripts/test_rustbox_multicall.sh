#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-normalize:2026-11-19 \
  exec "$root/scripts/run_tool.sh" python3 /work/scripts/test_rustbox_multicall.py \
    --repository /work \
    --coreutils-build /rustbox-coreutils/canonical-clang-no-security-compdb \
    --util-linux-build /rustbox-util-linux/canonical-clang-compdb \
    --rustbox /rustbox-coreutils/canonical-clang-no-security-compdb/src/rustbox \
    --output /work/work/analysis/rustbox-multicall-dispatch.json
