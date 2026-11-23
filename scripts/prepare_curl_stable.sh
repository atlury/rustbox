#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
base="$root/work/analysis/curl-8.23.0/translations/c2rust-0.22.1"
audit="$base/curl-8.23.0-normalized-audit"
stable="$base/curl-8.23.0-stable"

python3 -B "$root/scripts/modernize_c2rust_output.py" \
  --input "$audit" --output "$stable"
python3 -B "$root/scripts/finalize_curl_stable.py" --crate "$stable"

RUSTBOX_TOOL_IMAGE=rustbox-curl:2026-11-23 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    crate=/work/work/analysis/curl-8.23.0/translations/c2rust-0.22.1/curl-8.23.0-stable
    python3 /work/scripts/check_cargo_crate.py \
      --crate "$crate" --output "$crate/rustbox-cargo-check.json"
    cd "$crate"
    cargo build --release
  '
