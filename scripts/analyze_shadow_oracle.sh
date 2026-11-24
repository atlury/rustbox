#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-shadow:2026-11-24 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    export PYTHONDONTWRITEBYTECODE=1
    source=/work/work/upstream/shadow-4.20.4
    build=/rustbox-shadow/oracle-clang-18
    output=/work/work/analysis/shadow-4.20.4/analyzers
    database_dir=/rustbox-shadow/production-compdb
    database=$database_dir/compile_commands.json
    cppcheck_build=/rustbox-shadow/cppcheck-build
    rm -rf "$output" "$database_dir" "$cppcheck_build"
    mkdir -p "$output" "$database_dir" "$cppcheck_build"

    python3 - /work/work/analysis/shadow-4.20.4/oracle/clang-18-compile-commands.json \
      "$database" "$database_dir/sources.list" <<"PY"
import json,shlex,sys
from pathlib import Path
source_db,output_db,output_list=map(Path,sys.argv[1:])
signed=Path("/work/work/upstream/shadow-4.20.4")
records=json.loads(source_db.read_text())
selected=[]
sources=set()
for record in records:
    source=Path(record["file"]).resolve()
    if not source.is_relative_to(signed) or "tests" in source.parts:
        continue
    copied=dict(record)
    copied["file"]=str(source)
    if "arguments" not in copied:
        copied["arguments"]=shlex.split(copied.pop("command"))
    selected.append(copied)
    sources.add(source)
if len(selected) != 201 or len(sources) != 201:
    raise SystemExit(f"Shadow production closure changed: {len(selected)} actions, {len(sources)} sources")
output_db.write_text(json.dumps(selected,indent=2)+"\n")
output_list.write_text("".join(f"{source}\n" for source in sorted(sources)))
PY
    cp "$database" "$output/compile_commands.json"
    cp "$database_dir/sources.list" "$output/sources.list"

    set +e
    timeout --signal=TERM --kill-after=30s 1800s \
      cppcheck --enable=warning,style,performance,portability \
        --inline-suppr --suppress=missingIncludeSystem \
        --cppcheck-build-dir="$cppcheck_build" -j"$(nproc)" \
        --template="{file}:{line}:{column}: {severity}: {id}: {message}" \
        --project="$database" >"$output/cppcheck.log" 2>&1
    printf "%s\n" "$?" >"$output/cppcheck.status"

    timeout --signal=TERM --kill-after=30s 2400s \
      python3 /work/scripts/analyze_compile_database_gcc.py \
        --database "$database" --log "$output/gcc-analyzer.log" \
        --summary "$output/gcc-analyzer-summary.json" --jobs "$(nproc)" \
        >"$output/gcc-analyzer-driver.log" 2>&1
    printf "%s\n" "$?" >"$output/gcc-analyzer.status"

    timeout --signal=TERM --kill-after=30s 2400s \
      run-clang-tidy-18 -p "$database_dir" \
        -checks="clang-analyzer-*,bugprone-*,performance-*,portability-*" \
        -header-filter="^/work/work/upstream/shadow-4.20.4/" \
        >"$output/clang-analyzer-tidy.log" 2>&1
    printf "%s\n" "$?" >"$output/clang-analyzer-tidy.status"

    timeout --signal=TERM --kill-after=30s 600s \
      xargs flawfinder --minlevel=1 --quiet <"$database_dir/sources.list" \
        >"$output/flawfinder.log" 2>&1
    printf "%s\n" "$?" >"$output/flawfinder.status"

    timeout --signal=TERM --kill-after=30s 900s \
      xargs -n1 sparse -D_GNU_SOURCE -include "$build/config.h" \
        -I"$build" -I"$source" -I"$source/lib" -I"$source/libsubid" \
        <"$database_dir/sources.list" >"$output/sparse.log" 2>&1
    printf "%s\n" "$?" >"$output/sparse.status"
    set -e
    chmod -R a+rwX "$output"
  '
