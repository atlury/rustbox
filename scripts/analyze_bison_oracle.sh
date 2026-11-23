#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-bison:2026-11-23 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    source=/rustbox-bison/source-pristine
    volume=/rustbox-bison
    output=/work/work/analysis/bison-3.8.2/analyzers
    cppcheck_build=$volume/cppcheck-build
    database_dir=$volume/production-compdb
    database=$database_dir/compile_commands.json
    rm -rf "$output" "$cppcheck_build" "$database_dir"
    mkdir -p "$output" "$cppcheck_build" "$database_dir"

    python3 - /work/work/analysis/bison-3.8.2/oracle/clang-compile-commands.json \
      "$database" "$database_dir/sources.list" <<"PY"
import json,sys
from pathlib import Path
source_db,output_db,output_list=map(Path,sys.argv[1:])
records=json.loads(source_db.read_text())
records=[record for record in records
         if not record["file"].endswith(("/lib/main.c","/lib/yyerror.c"))]
sources=sorted({Path(record["file"]).resolve() for record in records})
root=Path("/rustbox-bison/source-pristine")
if len(records) != 152 or len(sources) != 152:
    raise SystemExit("GNU Bison production closure changed")
if any(not source.is_relative_to(root) for source in sources):
    raise SystemExit("GNU Bison production closure escapes signed source")
output_db.write_text(json.dumps(records,indent=2)+"\n")
output_list.write_text("".join(f"{source}\n" for source in sources))
PY
    cp "$database" "$output/compile_commands.json"
    cp "$database_dir/sources.list" "$output/sources.list"

    printf "%s\n" "cppcheck: 152 production translation units (10 minute bound)"
    set +e
    timeout --signal=TERM --kill-after=30s 600s \
      cppcheck --enable=warning,style,performance,portability \
        --inline-suppr --suppress=missingIncludeSystem \
        --cppcheck-build-dir="$cppcheck_build" -j"$(nproc)" \
        --template="{file}:{line}:{column}: {severity}: {id}: {message}" \
        --project="$database" >"$output/cppcheck.log" 2>&1
    cppcheck_status=$?
    set -e
    if ! grep -q "^152/152 files checked" "$output/cppcheck.log" \
        || grep -q "cppcheckError" "$output/cppcheck.log"; then
      printf "%s\n" \
        "incomplete: cppcheck did not finish lib/strversion.c within its bounded run" \
        >>"$output/cppcheck.log"
      cppcheck_status=124
    fi
    printf "%s\n" "$cppcheck_status" >"$output/cppcheck.status"

    printf "%s\n" "gcc -fanalyzer: production database (30 minute bound)"
    set +e
    timeout --signal=TERM --kill-after=30s 1800s \
      python3 /work/scripts/analyze_compile_database_gcc.py \
        --database "$database" --log "$output/gcc-analyzer.log" \
        --summary "$output/gcc-analyzer-summary.json" --jobs "$(nproc)" \
        >"$output/gcc-analyzer-driver.log" 2>&1
    gcc_status=$?
    set -e
    printf "%s\n" "$gcc_status" >"$output/gcc-analyzer.status"

    printf "%s\n" "clang-tidy/analyzer: production database (30 minute bound)"
    set +e
    timeout --signal=TERM --kill-after=30s 1800s \
      run-clang-tidy-18 -p "$database_dir" \
        -checks="clang-analyzer-*,bugprone-*,performance-*,portability-*" \
        -header-filter="^/rustbox-bison/source-pristine/(src|lib)/" \
        >"$output/clang-analyzer-tidy.log" 2>&1
    clang_status=$?
    set -e
    printf "%s\n" "$clang_status" >"$output/clang-analyzer-tidy.status"

    printf "%s\n" "flawfinder: production source closure (10 minute bound)"
    set +e
    timeout --signal=TERM --kill-after=30s 600s \
      xargs flawfinder --minlevel=1 --quiet < "$database_dir/sources.list" \
        >"$output/flawfinder.log" 2>&1
    flawfinder_status=$?
    set -e
    printf "%s\n" "$flawfinder_status" >"$output/flawfinder.status"

    printf "%s\n" "sparse: production source closure (10 minute bound)"
    set +e
    timeout --signal=TERM --kill-after=30s 600s \
      xargs -n1 sparse -DHAVE_CONFIG_H \
        -I"$volume/oracle-v3-clang" -I"$volume/oracle-v3-clang/lib" \
        -I"$source" -I"$source/src" -I"$source/lib" \
        -I/work/tools/sparse-compat \
        < "$database_dir/sources.list" >"$output/sparse.log" 2>&1
    sparse_status=$?
    set -e
    printf "%s\n" "$sparse_status" >"$output/sparse.status"
  '
