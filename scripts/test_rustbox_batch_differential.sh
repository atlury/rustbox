#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
binary=/rustbox-coreutils/canonical-clang-no-security-compdb/src/rustbox
set -- --reuse-passing
if [ -n "${RUSTBOX_MULTICALL_TEST_BINARY:-}" ]; then
    binary=/rustbox-test-elf/rustbox
    set --
fi
exec "$root/scripts/run_multicall_tool.sh" python3 /work/scripts/test_rustbox_batch_differential.py \
    --repository /work \
    --coreutils-root /rustbox-coreutils \
    --util-linux-build /rustbox-util-linux/canonical-clang-compdb \
    --rustbox "$binary" \
    --report-directory /work/work/analysis/rustbox-multicall-differential \
    --jobs 4 "$@" \
    --output /work/work/analysis/rustbox-multicall-differential.json
