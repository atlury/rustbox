#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-less:2026-11-22 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    source=/rustbox-less/source
    output=/work/work/analysis/less-710/analyzers
    database=/work/work/analysis/less-710/oracle/clang-compile-commands.json
    fanalyzer=/rustbox-less/analyzer-gcc
    rm -rf "$output" "$fanalyzer"
    mkdir -p "$output" "$fanalyzer"
    cp "$database" "$output/compile_commands.json"

    python3 - "$database" "$output/sources.list" <<"PY"
import json, sys
from pathlib import Path
database, output = map(Path, sys.argv[1:])
records = json.loads(database.read_text())
sources = sorted({Path(record["file"]).resolve() for record in records})
root = Path("/rustbox-less/source")
if len(records) != 38 or len(sources) != 38:
    raise SystemExit("Less production closure changed")
if any(not source.is_relative_to(root) for source in sources):
    raise SystemExit("Less production closure escapes canonical source")
output.write_text("".join(f"{source}\n" for source in sources))
PY

    cppcheck --enable=warning,style,performance,portability \
      --inline-suppr --suppress=missingIncludeSystem \
      --template="{file}:{line}:{column}: {severity}: {id}: {message}" \
      --project="$database" >"$output/cppcheck.log" 2>&1

    cd "$fanalyzer"
    CC=gcc CFLAGS="-O0 -g -fanalyzer -Wall -Wextra -fno-omit-frame-pointer" \
      "$source/configure" --prefix=/usr --with-regex=posix >"$output/gcc-configure.log" 2>&1
    make -j"$(nproc)" >"$output/gcc-analyzer.log" 2>&1

    run-clang-tidy-18 -p "$output" \
      -checks="clang-analyzer-*,bugprone-*,performance-*,portability-*" \
      -header-filter="^/rustbox-less/source/" \
      >"$output/clang-analyzer-tidy.log" 2>&1

    xargs flawfinder --minlevel=1 --quiet <"$output/sources.list" \
      >"$output/flawfinder.log" 2>&1

    if xargs -n1 sparse -I/source -I/rustbox-less/oracle-clang \
        -I/rustbox-less/source -I/work/tools/sparse-compat \
        -DBINDIR=\"/usr/bin\" -DLIBEXECDIR=\"/usr/libexec\" \
        -DSYSDIR=\"/usr/etc\" <"$output/sources.list" \
        >"$output/sparse.log" 2>&1
    then
      sparse_status=0
    else
      sparse_status=$?
    fi
    printf "%s\n" "$sparse_status" >"$output/sparse.status"

    if xargs -n1 splint -weak -I/rustbox-less/oracle-clang \
        -I/rustbox-less/source <"$output/sources.list" \
        >"$output/splint.log" 2>&1
    then
      splint_status=0
    else
      splint_status=$?
    fi
    printf "%s\n" "$splint_status" >"$output/splint.status"
  '
