#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-curl:2026-11-23 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    export PYTHONDONTWRITEBYTECODE=1
    source=/work/work/upstream/curl-8.23.0
    volume=/rustbox-curl
    output=/work/work/analysis/curl-8.23.0/analyzers
    database_dir=$volume/production-compdb
    database=$database_dir/compile_commands.json
    cppcheck_build=$volume/cppcheck-build
    rm -rf "$output" "$database_dir" "$cppcheck_build"
    mkdir -p "$output" "$database_dir" "$cppcheck_build"

    python3 - /work/work/analysis/curl-8.23.0/oracle/clang-compile-commands.json \
      "$database" "$database_dir/sources.list" <<"PY"
import json,sys
from pathlib import Path
source_db,output_db,output_list=map(Path,sys.argv[1:])
records=json.loads(source_db.read_text())
sources=sorted({Path(record["file"]).resolve() for record in records})
signed=Path("/work/work/upstream/curl-8.23.0")
generated=Path("/rustbox-curl/oracle-clang/src")
if len(records) != 477 or len(sources) != 240:
    raise SystemExit("curl production closure changed")
if any(not source.is_relative_to(signed) and not source.is_relative_to(generated)
       for source in sources):
    raise SystemExit("curl production closure escapes signed/generated roots")
output_db.write_text(json.dumps(records,indent=2)+"\n")
output_list.write_text("".join(f"{source}\n" for source in sources))
PY
    cp "$database" "$output/compile_commands.json"
    cp "$database_dir/sources.list" "$output/sources.list"

    printf "%s\n" "cppcheck: 477 exact production actions (20 minute bound)"
    set +e
    timeout --signal=TERM --kill-after=30s 1200s \
      cppcheck --enable=warning,style,performance,portability \
        --inline-suppr --suppress=missingIncludeSystem \
        --cppcheck-build-dir="$cppcheck_build" -j"$(nproc)" \
        --template="{file}:{line}:{column}: {severity}: {id}: {message}" \
        --project="$database" >"$output/cppcheck.log" 2>&1
    cppcheck_status=$?
    set -e
    printf "%s\n" "$cppcheck_status" >"$output/cppcheck.status"

    printf "%s\n" "gcc -fanalyzer: 477 exact production actions (60 minute bound)"
    set +e
    timeout --signal=TERM --kill-after=30s 3600s \
      python3 /work/scripts/analyze_compile_database_gcc.py \
        --database "$database" --log "$output/gcc-analyzer.log" \
        --summary "$output/gcc-analyzer-summary.json" --jobs "$(nproc)" \
        >"$output/gcc-analyzer-driver.log" 2>&1
    gcc_status=$?
    set -e
    printf "%s\n" "$gcc_status" >"$output/gcc-analyzer.status"

    printf "%s\n" "clang-tidy/analyzer: 477 exact production actions (60 minute bound)"
    set +e
    timeout --signal=TERM --kill-after=30s 3600s \
      run-clang-tidy-18 -p "$database_dir" \
        -checks="clang-analyzer-*,bugprone-*,performance-*,portability-*" \
        -header-filter="^(/work/work/upstream/curl-8.23.0|/rustbox-curl/oracle-clang)/" \
        >"$output/clang-analyzer-tidy.log" 2>&1
    clang_status=$?
    set -e
    printf "%s\n" "$clang_status" >"$output/clang-analyzer-tidy.status"

    printf "%s\n" "flawfinder: 240 unique production sources (10 minute bound)"
    set +e
    timeout --signal=TERM --kill-after=30s 600s \
      xargs flawfinder --minlevel=1 --quiet <"$database_dir/sources.list" \
        >"$output/flawfinder.log" 2>&1
    flawfinder_status=$?
    set -e
    printf "%s\n" "$flawfinder_status" >"$output/flawfinder.status"

    printf "%s\n" "sparse: 240 unique production sources (10 minute bound)"
    set +e
    timeout --signal=TERM --kill-after=30s 600s \
      xargs -n1 sparse -DHAVE_CONFIG_H -DCURL_STATICLIB -D_GNU_SOURCE \
        -I"$volume/oracle-clang/lib" -I"$source/include" \
        -I"$source/lib" -I"$source/src" \
        <"$database_dir/sources.list" >"$output/sparse.log" 2>&1
    sparse_status=$?
    set -e
    printf "%s\n" "$sparse_status" >"$output/sparse.status"
  '
