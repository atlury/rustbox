#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
translation=/work/work/analysis/coreutils-9.12/translations/c2rust-0.22.1/true-false-stable
RUSTBOX_TOOL_IMAGE=rustbox-normalize:2026-11-19 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    translation=$1
    cd "$translation"
    cargo build --release
    python3 /work/scripts/link_coreutils_true_false_hybrid.py \
      --build /rustbox-coreutils/canonical-clang-compdb \
      --rust-library "$translation/target/release/libtrue_false_reachable.a"
  ' sh "$translation"
