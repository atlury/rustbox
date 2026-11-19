#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-normalize:2026-11-19 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    source=/work/work/upstream/zlib-1.4
    analysis=/work/work/analysis/zlib-1.4/analyzers
    gcc_build=/work/work/analysis/zlib-1.4/canonical-gcc-analyzer
    clang_build=/work/work/analysis/zlib-1.4/canonical-clang-scan
    mkdir -p "$analysis" "$gcc_build" "$clang_build"

    cppcheck --enable=warning,style,performance,portability \
      --inline-suppr --suppress=missingIncludeSystem \
      --template="{file}:{line}:{column}: {severity}: {id}: {message}" \
      --project=/work/work/analysis/zlib-1.4/canonical-clang-make/compile_commands.json \
      >"$analysis/cppcheck.log" 2>&1

    cd "$gcc_build"
    CC=gcc CFLAGS="-O0 -g -fanalyzer -Wall -Wextra" \
      "$source/configure" --static >"$analysis/gcc-analyzer-configure.log" 2>&1
    make -B -j"$(nproc)" >"$analysis/gcc-analyzer.log" 2>&1

    cd "$clang_build"
    CC=clang-18 CFLAGS="-O0 -g" "$source/configure" --static \
      >"$analysis/clang-analyzer-configure.log" 2>&1
    scan-build-18 -o "$analysis/scan-build" --keep-empty \
      make -B -j"$(nproc)" >"$analysis/clang-analyzer.log" 2>&1

    run-clang-tidy-18 \
      -p /work/work/analysis/zlib-1.4/canonical-clang-make \
      -checks="clang-analyzer-*,bugprone-*,performance-*,portability-*" \
      -header-filter="^/work/work/upstream/zlib-1.4/" \
      >"$analysis/clang-tidy.log" 2>&1

    flawfinder --minlevel=1 --quiet "$source"/*.c "$source"/test/*.c \
      >"$analysis/flawfinder.log" 2>&1
  '
