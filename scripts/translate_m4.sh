#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
analysis="$root/work/analysis/m4-1.4.21"
database=/rustbox-m4/normalized-clang/compile_commands.json
output="$analysis/translations/c2rust-0.22.1/m4-1.4.21-normalized-audit"

RUSTBOX_TOOL_IMAGE=rustbox-normalize:2026-11-19 \
  "$root/scripts/run_tool.sh" python3 /work/scripts/prepare_m4_c2rust.py \
    --database "$database" \
    --output /work/work/analysis/m4-1.4.21/normalized/c2rust-compdb/compile_commands.json

case "$output" in
  "$analysis/translations/c2rust-0.22.1/"*)
    test ! -e "$output" || rm -rf -- "$output"
    ;;
  *) exit 2 ;;
esac
mkdir -p "$output"

RUSTBOX_TOOL_IMAGE=rustbox-normalize:2026-11-19 \
  exec "$root/scripts/run_tool.sh" c2rust transpile \
    --output-dir /work/work/analysis/m4-1.4.21/translations/c2rust-0.22.1/m4-1.4.21-normalized-audit \
    --emit-build-files \
    --emit-c-decl-map \
    --fail-on-error \
    --disable-rustfmt \
    --overwrite-existing \
    --preserve-unused-functions \
    /rustbox-m4/normalized-source/src/builtin.c \
    /rustbox-m4/normalized-source/src/debug.c \
    /rustbox-m4/normalized-source/src/eval.c \
    /rustbox-m4/normalized-source/src/format.c \
    /rustbox-m4/normalized-source/src/freeze.c \
    /rustbox-m4/normalized-source/src/input.c \
    /rustbox-m4/normalized-source/src/m4.c \
    /rustbox-m4/normalized-source/src/macro.c \
    /rustbox-m4/normalized-source/src/output.c \
    /rustbox-m4/normalized-source/src/path.c \
    /rustbox-m4/normalized-source/src/symtab.c \
    -- \
    -I/rustbox-m4/normalized-source/lib \
    -I/rustbox-m4/normalized-clang/lib \
    -O2 -g -fno-omit-frame-pointer -DRUSTBOX_MULTICALL=1
