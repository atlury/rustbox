#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
exec docker run --rm --platform linux/amd64 \
  --volume "$root:/work" \
  --volume rustbox-e2fsprogs-1.47.4:/rustbox-e2fsprogs \
  --workdir /work rustbox-e2fsprogs:2026-11-24 sh -eu -c '
    export PYTHONDONTWRITEBYTECODE=1
    source=/work/work/upstream/e2fsprogs-1.47.4
    build=/rustbox-e2fsprogs/oracle-clang-18
    output=/work/work/analysis/e2fsprogs-1.47.4/analyzers
    database_dir=/rustbox-e2fsprogs/analysis-compdb
    database=$database_dir/compile_commands.json
    cppcheck_build=/rustbox-e2fsprogs/cppcheck-build
    rm -rf "$output" "$database_dir" "$cppcheck_build"
    mkdir -p "$output" "$database_dir" "$cppcheck_build"

    python3 - /work/work/analysis/e2fsprogs-1.47.4/oracle/clang-18-compile-commands.json \
      "$database" "$database_dir/sources.list" <<"PY"
import json, shlex, sys
from collections import defaultdict
from pathlib import Path
source_db, output_db, output_list = map(Path, sys.argv[1:])
records = json.loads(source_db.read_text())
grouped = defaultdict(list)
for record in records:
    path = (Path(record["directory"]) / record["file"]).resolve()
    grouped[path].append(record)
selected = []
for path in sorted(grouped):
    def action_key(item):
        arguments = item.get("arguments") or shlex.split(item["command"])
        return (int("-c" in arguments), int("-cc1" not in arguments), len(arguments))
    record = max(grouped[path], key=action_key)
    copied = dict(record)
    copied["file"] = str(path)
    if "arguments" not in copied:
        copied["arguments"] = shlex.split(copied.pop("command"))
    selected.append(copied)
if len(records) != 241 or len(selected) != 232:
    raise SystemExit(
        f"E2fsprogs compile closure changed: {len(records)} actions, {len(selected)} sources"
    )
output_db.write_text(json.dumps(selected, indent=2) + "\n")
output_list.write_text("".join(f"{path}\n" for path in sorted(grouped)))
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
        -header-filter="^(/work/work/upstream/e2fsprogs-1.47.4|/rustbox-e2fsprogs/oracle-clang-18)/" \
        >"$output/clang-analyzer-tidy.log" 2>&1
    printf "%s\n" "$?" >"$output/clang-analyzer-tidy.status"

    timeout --signal=TERM --kill-after=30s 900s \
      env PYTHONUTF8=0 LC_ALL=fr_FR.iso88591 \
      xargs flawfinder --minlevel=1 --quiet <"$database_dir/sources.list" \
        >"$output/flawfinder.log" 2>&1
    printf "%s\n" "$?" >"$output/flawfinder.status"

    timeout --signal=TERM --kill-after=30s 900s \
      xargs -n1 sparse -D_GNU_SOURCE -include "$build/config.h" \
        -I"$build" -I"$source" -I"$source/lib" \
        -I"$build/lib" -I/usr/include/fuse3 \
        <"$database_dir/sources.list" >"$output/sparse.log" 2>&1
    printf "%s\n" "$?" >"$output/sparse.status"
    set -e
    chmod -R a+rwX "$output"
  '
