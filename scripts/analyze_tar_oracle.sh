#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-tar:2026-11-22 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    volume=/rustbox-tar
    source=$volume/analyzer-source
    output=/work/work/analysis/tar-1.35/analyzers
    database=/work/work/analysis/tar-1.35/oracle/gcc-compile-commands.json
    rm -rf "$source" "$output"
    cp -a "$volume/source-gcc" "$source"
    mkdir -p "$output"

    python3 - "$database" "$output/sources.list" "$output/c-sources.list" <<"PY"
import hashlib,json,sys
from pathlib import Path
database,output,c_output=map(Path,sys.argv[1:])
records=json.loads(database.read_text())
root=Path("/rustbox-tar/source-gcc")
sources=sorted({Path(record["file"]).resolve() for record in records})
relative=[source.relative_to(root).as_posix() for source in sources]
digest=hashlib.sha256(("\n".join(relative)+"\n").encode()).hexdigest()
if len(records) != 197 or len(sources) != 197:
    raise SystemExit("GNU tar production closure changed")
if digest != "31dd9e972f2643378de2dda2d1b9f8b615549ed254648c9e2cdd57c453a28175":
    raise SystemExit("GNU tar production closure digest changed")
output.write_text("".join(f"{source}\n" for source in sources))
c_output.write_text("".join(f"{source}\n" for source in sources if source.suffix == ".c"))
PY
    cp "$database" "$output/compile_commands.json"

    cppcheck --enable=warning,style,performance,portability \
      --inline-suppr --suppress=missingIncludeSystem \
      --template="{file}:{line}:{column}: {severity}: {id}: {message}" \
      --project="$database" >"$output/cppcheck.log" 2>&1

    cd "$source"
    make clean >/dev/null
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
        -header-filter="^/rustbox-tar/source-gcc/(gnu|lib|rmt|src)/" \
        >"$output/clang-analyzer-tidy.log" 2>&1
    then
      clang_status=0
    else
      clang_status=$?
    fi
    printf "%s\n" "$clang_status" >"$output/clang-analyzer-tidy.status"

    if xargs flawfinder --minlevel=1 --quiet <"$output/c-sources.list" \
        >"$output/flawfinder.log" 2>&1
    then
      flawfinder_status=0
    else
      flawfinder_status=$?
    fi
    printf "%s\n" "$flawfinder_status" >"$output/flawfinder.status"

    sparse_source=$volume/sparse-source
    rm -rf "$sparse_source"
    cp -a "$volume/source-gcc" "$sparse_source"
    scratch_header=$sparse_source/gnu/malloc/scratch_buffer.h
    grep -q "union { max_align_t __align; char __c\[1024\]; } __space;" \
      "$scratch_header"
    sed -i \
      "s/union { max_align_t __align;/union { long double __align;/" \
      "$scratch_header"
    cd "$sparse_source"
    make clean >/dev/null
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
