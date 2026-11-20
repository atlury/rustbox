#!/bin/sh
# SPDX-License-Identifier: BSD-2-Clause
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-file:2026-11-20 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    readonly source=/rustbox-file/source
    readonly volume=/rustbox-file
    readonly output=/work/work/analysis/file-5.48/analyzers
    readonly gcc_build=$volume/analyzer-gcc
    readonly database_dir=$volume/production-compdb
    readonly database=$database_dir/compile_commands.json
    rm -rf "$output" "$gcc_build" "$database_dir"
    mkdir -p "$output" "$database_dir"

    cp "$volume/canonical-clang/compile_commands.json" "$database"
    python3 - "$database" "$database_dir/sources.list" <<"PY"
import json,sys
from pathlib import Path
database=Path(sys.argv[1]); output=Path(sys.argv[2])
records=json.loads(database.read_text())
sources=sorted({Path(record["file"]).resolve() for record in records})
if len(records) != 25 or len(sources) != 25:
    raise SystemExit("File production closure changed")
if any(not source.is_relative_to(Path("/rustbox-file/source/src")) for source in sources):
    raise SystemExit("File production closure escapes source/src")
output.write_text("".join(f"{source}\n" for source in sources))
PY
    cp "$database" "$output/compile_commands.json"
    cp "$database_dir/sources.list" "$output/sources.list"

    cppcheck --enable=warning,style,performance,portability \
      --inline-suppr --suppress=missingIncludeSystem \
      --template="{file}:{line}:{column}: {severity}: {id}: {message}" \
      --project="$database" >"$output/cppcheck.log" 2>&1

    mkdir "$gcc_build"
    cd "$gcc_build"
    CC=gcc CFLAGS="-O0 -g -fanalyzer -fno-omit-frame-pointer" \
      "$source/configure" --disable-dependency-tracking \
      --disable-shared --enable-static >"$output/gcc-analyzer-setup.log" 2>&1
    make -j"$(nproc)" >"$output/gcc-analyzer.log" 2>&1

    run-clang-tidy-18 -p "$database_dir" \
      -checks="clang-analyzer-*,bugprone-*,performance-*,portability-*" \
      -header-filter="^/rustbox-file/source/src/" \
      >"$output/clang-analyzer-tidy.log" 2>&1

    xargs flawfinder --minlevel=1 --quiet < "$database_dir/sources.list" \
      >"$output/flawfinder.log" 2>&1

    xargs -n1 sparse \
      -DHAVE_CONFIG_H -I"$volume/canonical-clang" \
      -I"$volume/canonical-clang/src" -I"$source/src" \
      -DMAGIC=\"/usr/local/share/misc/magic\" \
      < "$database_dir/sources.list" >"$output/sparse.log" 2>&1
  '
