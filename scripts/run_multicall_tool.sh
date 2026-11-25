#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# The release linker and package regressions need the same Linux runtime libraries.
set -eu
root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
if [ -n "${RUSTBOX_MULTICALL_TEST_BINARY:-}" ]; then
    set -- --multicall-test-binary "$RUSTBOX_MULTICALL_TEST_BINARY" "$@"
fi
RUSTBOX_TOOL_IMAGE=rustbox-e2fsprogs:2026-11-24 exec "$root/scripts/run_tool.sh" "$@"
