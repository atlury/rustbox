#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
analysis="$root/work/analysis/zlib-1.4"
database="$analysis/normalized/clang-make/compile_commands.json"
slice="$analysis/normalized/c2rust-compile-commands.json"
output="$analysis/translations/c2rust-0.22.1/zlib-1.4-normalized-audit"

test -s "$database" || {
  echo "run scripts/build_zlib_normalized.sh first" >&2
  exit 1
}
"$root/scripts/prepare_zlib_c2rust.py" --database "$database" --output "$slice"
case "$output" in
  "$analysis/translations/c2rust-0.22.1/"*)
    test ! -e "$output" || rm -rf -- "$output"
    ;;
  *) exit 2 ;;
esac
mkdir -p "$output"

set -- c2rust transpile \
    --output-dir /work/work/analysis/zlib-1.4/translations/c2rust-0.22.1/zlib-1.4-normalized-audit \
    --emit-build-files \
    --emit-c-decl-map \
    --fail-on-error \
    --disable-rustfmt \
    --overwrite-existing \
    --preserve-unused-functions \
    /work/work/analysis/zlib-1.4/normalized/source/adler32.c \
    /work/work/analysis/zlib-1.4/normalized/source/compress.c \
    /work/work/analysis/zlib-1.4/normalized/source/crc32.c \
    /work/work/analysis/zlib-1.4/normalized/source/deflate.c \
    /work/work/analysis/zlib-1.4/normalized/source/gzclose.c \
    /work/work/analysis/zlib-1.4/normalized/source/gzlib.c \
    /work/work/analysis/zlib-1.4/normalized/source/gzread.c \
    /work/work/analysis/zlib-1.4/normalized/source/gzwrite.c \
    /work/work/analysis/zlib-1.4/normalized/source/infback.c \
    /work/work/analysis/zlib-1.4/normalized/source/inffast.c \
    /work/work/analysis/zlib-1.4/normalized/source/inflate.c \
    /work/work/analysis/zlib-1.4/normalized/source/inftrees.c \
    /work/work/analysis/zlib-1.4/normalized/source/trees.c \
    /work/work/analysis/zlib-1.4/normalized/source/uncompr.c \
    /work/work/analysis/zlib-1.4/normalized/source/zutil.c \
    -- \
    -O2 -g -fno-omit-frame-pointer -fPIC \
    -D_LARGEFILE64_SOURCE=1 -DHAVE_HIDDEN \
    -I/work/work/analysis/zlib-1.4/normalized/clang-make \
    -include zconf.h

# C2Rust 0.22.1's AST exporter misroutes this Bear JSON filename through
# ClangTool's directory-only -p interface.  The selector above proves all 15
# production commands have the same flags, so pass those exact flags directly.
RUSTBOX_TOOL_IMAGE=rustbox-normalize:2026-11-19 \
  exec "$root/scripts/run_tool.sh" "$@"
