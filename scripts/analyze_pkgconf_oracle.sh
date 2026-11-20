#!/bin/sh
# SPDX-License-Identifier: ISC
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-normalize:2026-11-19 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    readonly source=/rustbox-pkgconf/source
    readonly volume=/rustbox-pkgconf
    readonly output=/work/work/analysis/pkgconf-3.0.11/analyzers
    readonly gcc_build=$volume/analyzer-gcc
    readonly database_dir=$volume/production-compdb
    readonly database=$database_dir/compile_commands.json
    rm -rf "$output" "$gcc_build" "$database_dir"
    mkdir -p "$output" "$database_dir"

    python3 /work/scripts/prepare_pkgconf_compdb.py \
      --database "$volume/canonical-clang-static/compile_commands.json" \
      --output "$database" \
      --source-list "$database_dir/sources.list"
    cp "$database" "$output/compile_commands.json"
    cp "$database_dir/sources.list" "$output/sources.list"

    cppcheck --enable=warning,style,performance,portability \
      --inline-suppr --suppress=missingIncludeSystem \
      --template="{file}:{line}:{column}: {severity}: {id}: {message}" \
      --project="$database" >"$output/cppcheck.log" 2>&1

    CC=gcc meson setup "$gcc_build" "$source" \
      --buildtype=debug --default-library=static -Danalyzer=true -Db_lto=false \
      >"$output/gcc-analyzer-setup.log" 2>&1
    meson compile -C "$gcc_build" -j "$(nproc)" \
      pkgconf:executable bomtool pccritic spdxtool >"$output/gcc-analyzer.log" 2>&1

    run-clang-tidy-18 -p "$database_dir" \
      -checks="clang-analyzer-*,bugprone-*,performance-*,portability-*" \
      -header-filter="^/rustbox-pkgconf/source/(cli|libpkgconf)/" \
      >"$output/clang-analyzer-tidy.log" 2>&1

    xargs flawfinder --minlevel=1 --quiet < "$database_dir/sources.list" \
      >"$output/flawfinder.log" 2>&1

    xargs -n1 sparse \
          -I"$source" -I"$source/cli" -I"$source/cli/spdxtool" \
          -I"$volume/canonical-clang-static" \
          -D_ATFILE_SOURCE -D_BSD_SOURCE -D_DARWIN_C_SOURCE \
          -D_DEFAULT_SOURCE -D_POSIX_C_SOURCE=200809L -D_XOPEN_SOURCE=700 \
          -DPKGCONFIG_IS_STATIC -DLIBPKGCONF_EXPORT \
      < "$database_dir/sources.list" \
      >"$output/sparse.log" 2>&1
  '
