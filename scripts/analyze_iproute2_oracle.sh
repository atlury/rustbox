#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-iproute2:2026-11-24 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    export PYTHONDONTWRITEBYTECODE=1
    build=/rustbox-iproute2/oracle-clang-18
    output=/work/work/analysis/iproute2-7.3.0/analyzers
    database_dir=/rustbox-iproute2/production-compdb
    database=$database_dir/compile_commands.json
    cppcheck_build=/rustbox-iproute2/cppcheck-build
    rm -rf "$output" "$database_dir" "$cppcheck_build"
    mkdir -p "$output" "$database_dir" "$cppcheck_build"

    python3 - /work/work/analysis/iproute2-7.3.0/oracle/clang-18-compile-commands.json \
      "$database" "$database_dir/sources.list" <<"PY"
import json, shlex, sys
from pathlib import Path
source_db, output_db, output_list = map(Path, sys.argv[1:])
build = Path("/rustbox-iproute2/oracle-clang-18")
records = json.loads(source_db.read_text())
selected = []
sources = set()
for record in records:
    source = (Path(record["directory"]) / record["file"]).resolve()
    relative = source.relative_to(build)
    if relative.parts[0] == "netem":
        continue
    if source in sources:
        continue
    copied = dict(record)
    copied["file"] = str(source)
    if "arguments" not in copied:
        copied["arguments"] = shlex.split(copied.pop("command"))
    selected.append(copied)
    sources.add(source)
if len(selected) != 260 or len(sources) != 260:
    raise SystemExit(
        f"IPRoute2 production closure changed: {len(selected)} actions, {len(sources)} sources"
    )
output_db.write_text(json.dumps(selected, indent=2) + "\n")
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

    timeout --signal=TERM --kill-after=30s 3600s \
      python3 /work/scripts/analyze_compile_database_gcc.py \
        --database "$database" --log "$output/gcc-analyzer.log" \
        --summary "$output/gcc-analyzer-summary.json" --jobs "$(nproc)" \
        >"$output/gcc-analyzer-driver.log" 2>&1
    printf "%s\n" "$?" >"$output/gcc-analyzer.status"

    timeout --signal=TERM --kill-after=30s 3600s \
      run-clang-tidy-18 -p "$database_dir" \
        -checks="clang-analyzer-*,bugprone-*,performance-*,portability-*" \
        -header-filter="^/rustbox-iproute2/oracle-clang-18/" \
        >"$output/clang-analyzer-tidy.log" 2>&1
    printf "%s\n" "$?" >"$output/clang-analyzer-tidy.status"

    timeout --signal=TERM --kill-after=30s 900s \
      xargs flawfinder --minlevel=1 --quiet <"$database_dir/sources.list" \
        >"$output/flawfinder.log" 2>&1
    printf "%s\n" "$?" >"$output/flawfinder.status"

    timeout --signal=TERM --kill-after=30s 900s \
      xargs -n1 sparse -D_GNU_SOURCE -D_FILE_OFFSET_BITS=64 \
        -I"$build/include" -I"$build/include/uapi" \
        <"$database_dir/sources.list" >"$output/sparse.log" 2>&1
    printf "%s\n" "$?" >"$output/sparse.status"
    set -e
    chmod -R a+rwX "$output"
  '
