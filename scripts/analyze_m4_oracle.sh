#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-normalize:2026-11-19 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    readonly source=/rustbox-m4/source
    readonly volume=/rustbox-m4
    readonly output=/work/work/analysis/m4-1.4.21/analyzers
    readonly gcc_build=$volume/analyzer-gcc
    readonly database_dir=$volume/production-compdb
    readonly database=$database_dir/compile_commands.json
    mkdir -p "$output"
    rm -rf "$gcc_build" "$database_dir"
    mkdir -p "$database_dir"

    python3 /work/scripts/prepare_m4_compdb.py \
      --database "$volume/canonical-clang/compile_commands.json" \
      --output "$database"

    cppcheck --enable=warning,style,performance,portability \
      --inline-suppr --suppress=missingIncludeSystem \
      --template="{file}:{line}:{column}: {severity}: {id}: {message}" \
      --project="$database" \
      >"$output/cppcheck.log" 2>&1

    mkdir "$gcc_build"
    cd "$gcc_build"
    CC=gcc CFLAGS="-O0 -g -fanalyzer -Wall -Wextra" \
      "$source/configure" --disable-dependency-tracking \
      >"$output/gcc-analyzer-configure.log" 2>&1
    make -C lib -j"$(nproc)" >"$output/gcc-analyzer.log" 2>&1
    make -C src -j"$(nproc)" >>"$output/gcc-analyzer.log" 2>&1

    run-clang-tidy-18 -p "$database_dir" \
      -checks="clang-analyzer-*,bugprone-*,performance-*,portability-*" \
      -header-filter="^/rustbox-m4/source/(src|lib)/" \
      >"$output/clang-analyzer-tidy.log" 2>&1

    jq -r ".[] | .file" "$database" | sort -u \
      | xargs flawfinder --minlevel=1 --quiet \
      >"$output/flawfinder.log" 2>&1
  '
