#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
crate=/work/work/analysis/gawk-5.4.0/translations/c2rust-0.22.1/gawk-5.4.0-stable
log=/work/work/analysis/gawk-5.4.0/translations/c2rust-0.22.1/stable-cargo-check.log

test -s "$root/work/analysis/gawk-5.4.0/translations/c2rust-0.22.1/gawk-5.4.0-stable/Cargo.toml" || {
  echo "run scripts/prepare_gawk_stable.sh first" >&2
  exit 1
}

RUSTBOX_TOOL_IMAGE=rustbox-gawk:2026-11-22 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    cd "$1"
    RUSTUP_TOOLCHAIN=1.99.0 cargo generate-lockfile >"$2" 2>&1
    RUSTUP_TOOLCHAIN=1.99.0 cargo check --locked >>"$2" 2>&1
    grep -q "Finished .* profile" "$2"
  ' sh "$crate" "$log"
