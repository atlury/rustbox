#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-normalize:2026-11-19 \
  exec "$root/scripts/run_tool.sh" python3 /work/scripts/link_rustbox_multicall.py \
    --repository /work \
    --coreutils-build /rustbox-coreutils/canonical-clang-no-security-compdb \
    --util-linux-build /rustbox-util-linux/canonical-clang-compdb \
    --m4-rust-library /work/work/analysis/m4-1.4.21/translations/c2rust-0.22.1/m4-1.4.21-stable/target/release/libm4_1_4_21_normalized_audit.a \
    --m4-support-library /rustbox-m4/normalized-clang/lib/libm4.a \
    --link-report /work/work/analysis/rustbox-multicall-link.json
