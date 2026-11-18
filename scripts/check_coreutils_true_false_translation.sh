#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
output=/work/work/analysis/coreutils-9.12/translations/c2rust-0.22.1/true-false
test -s "$root/work/analysis/coreutils-9.12/translations/c2rust-0.22.1/true-false/Cargo.toml" || {
  echo "run scripts/translate_coreutils_true_false.sh first" >&2
  exit 1
}
RUSTBOX_TOOL_IMAGE=rustbox-normalize:2026-11-19 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    cd "$1"
    RUSTUP_TOOLCHAIN=nightly-2023-04-15 cargo check
  ' sh "$output"
