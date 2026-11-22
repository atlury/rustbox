#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-tar:2026-11-22 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    volume=/rustbox-ncurses
    source=$volume/analyzer-source
    sparse_source=$volume/sparse-source
    output=/work/work/analysis/ncurses-6.6/analyzers
    database=/work/work/analysis/ncurses-6.6/oracle/gcc-compile-commands.json
    rm -rf "$source" "$sparse_source" "$output"
    cp -a "$volume/source-gcc" "$source"
    mkdir -p "$output"

    python3 - "$database" "$output/compile_commands.json" \
      "$output/sources.list" <<"PY"
import hashlib,json,sys
from pathlib import Path
database,deduplicated,output=map(Path,sys.argv[1:])
records=json.loads(database.read_text())
root=Path("/rustbox-ncurses/source-gcc")
selected={}
for record in records:
    source=Path(record["file"]).resolve()
    selected.setdefault(source, record)
sources=sorted(selected)
relative=[source.relative_to(root).as_posix() for source in sources]
digest=hashlib.sha256(("\n".join(relative)+"\n").encode()).hexdigest()
if len(records) != 514 or len(sources) != 264:
    raise SystemExit("Ncurses production closure changed")
if digest != "1bc8f0759a62f64488c020bf908e391bd35cc5b637959b3b837d022696609eaf":
    raise SystemExit("Ncurses production closure digest changed")
deduplicated.write_text(json.dumps([selected[source] for source in sources], indent=2)+"\n")
output.write_text("".join(f"{source}\n" for source in sources))
PY

    cppcheck --enable=warning,style,performance,portability \
      --inline-suppr --suppress=missingIncludeSystem \
      --template="{file}:{line}:{column}: {severity}: {id}: {message}" \
      --project="$output/compile_commands.json" >"$output/cppcheck.log" 2>&1

    cd "$source"
    make clean >/dev/null
    make -j"$(nproc)" sources >/dev/null
    if make -j"$(nproc)" CC=gcc \
        CFLAGS="-O0 -g -fanalyzer -Wall -Wextra -fno-omit-frame-pointer" \
        >"$output/gcc-analyzer.log" 2>&1
    then
      gcc_status=0
    else
      gcc_status=$?
    fi
    printf "%s\n" "$gcc_status" >"$output/gcc-analyzer.status"

    if run-clang-tidy-18 -p "$output" \
        -checks="clang-analyzer-*,bugprone-*,performance-*,portability-*" \
        -header-filter="^/rustbox-ncurses/source-gcc/(form|include|menu|ncurses|panel|progs)/" \
        >"$output/clang-analyzer-tidy.log" 2>&1
    then
      clang_status=0
    else
      clang_status=$?
    fi
    printf "%s\n" "$clang_status" >"$output/clang-analyzer-tidy.status"

    if xargs flawfinder --minlevel=1 --quiet <"$output/sources.list" \
        >"$output/flawfinder.log" 2>&1
    then
      flawfinder_status=0
    else
      flawfinder_status=$?
    fi
    printf "%s\n" "$flawfinder_status" >"$output/flawfinder.status"

    cp -a "$volume/source-gcc" "$sparse_source"
    cd "$sparse_source"
    make clean >/dev/null
    make -j"$(nproc)" sources >/dev/null
    if REAL_CC=gcc make -j"$(nproc)" CC=cgcc \
        CFLAGS="-O2 -g -fno-omit-frame-pointer" \
        >"$output/sparse.log" 2>&1
    then
      sparse_status=0
    else
      sparse_status=$?
    fi
    printf "%s\n" "$sparse_status" >"$output/sparse.status"
  '
