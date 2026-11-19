#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
"$root/scripts/provision_coreutils_source.sh"
mkdir -p "$root/work/analysis/coreutils-9.12/canonical-gcc"

exec "$root/scripts/run_tool.sh" sh -eu -c '
  source=/rustbox-source/coreutils-9.12
  build=/rustbox-coreutils/canonical-gcc-compdb
  output=/work/work/analysis/coreutils-9.12/canonical-gcc
  mkdir -p "$build" "$output"
  cd "$build"
  if test ! -f Makefile; then
    FORCE_UNSAFE_CONFIGURE=1 CC=gcc CFLAGS="-O1 -g" \
      "$source/configure" \
      --enable-install-program=arch,hostname,kill,uptime \
      --enable-single-binary=symlinks
  fi
  if test ! -s compile_commands.json; then
    bear --output compile_commands.json -- make -j"$(nproc)"
  else
    make -j"$(nproc)"
  fi
  python3 /work/scripts/summarize_compdb.py \
    --database compile_commands.json \
    --source-root "$source" \
    --build-root "$build" \
    --compiler-family gcc \
    --output "$output/summary.json"
  cp compile_commands.json "$output/compile_commands.json"
'
