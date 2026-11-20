#!/bin/sh
# SPDX-License-Identifier: ISC
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
analysis="$root/work/analysis/pkgconf-3.0.11"
database="$analysis/normalized/c2rust-compdb/compile_commands.json"
output="$analysis/translations/c2rust-0.22.1/pkgconf-3.0.11-normalized-audit"

RUSTBOX_TOOL_IMAGE=rustbox-normalize:2026-11-19 \
  "$root/scripts/run_tool.sh" python3 /work/scripts/prepare_pkgconf_c2rust.py \
    --database /rustbox-pkgconf/normalized-clang-static/compile_commands.json \
    --output /work/work/analysis/pkgconf-3.0.11/normalized/c2rust-compdb/compile_commands.json

case "$output" in
  "$analysis/translations/c2rust-0.22.1/"*)
    test ! -e "$output" || rm -rf -- "$output"
    ;;
  *) exit 2 ;;
esac
mkdir -p "$output"

RUSTBOX_TOOL_IMAGE=rustbox-normalize:2026-11-19 \
  exec "$root/scripts/run_tool.sh" python3 /work/scripts/run_pkgconf_c2rust.py \
    --database /work/work/analysis/pkgconf-3.0.11/normalized/c2rust-compdb/compile_commands.json \
    --output /work/work/analysis/pkgconf-3.0.11/translations/c2rust-0.22.1/pkgconf-3.0.11-normalized-audit
