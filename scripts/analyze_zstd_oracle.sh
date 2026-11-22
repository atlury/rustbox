#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-zstd:2026-11-22 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    release=/work/work/upstream/zstd-1.5.7
    source=/rustbox-zstd/analyzer-source
    output=/work/work/analysis/zstd-1.5.7/analyzers
    database=/work/work/analysis/zstd-1.5.7/oracle/clang-compile-commands.json
    feature_flags="HAVE_ZLIB=0 HAVE_LZMA=0 HAVE_LZ4=0 BACKTRACE=0"
    rm -rf "$source" "$output"
    cp -a "$release" "$source"
    mkdir -p "$output"

    python3 - "$database" "$output/sources.list" "$output/c-sources.list" <<"PY"
import hashlib,json,sys
from pathlib import Path
database,output,c_output=map(Path,sys.argv[1:])
records=json.loads(database.read_text())
root=Path("/rustbox-zstd/source-clang")
sources=sorted({Path(record["file"]).resolve() for record in records})
relative=[source.relative_to(root).as_posix() for source in sources]
digest=hashlib.sha256(("\n".join(relative)+"\n").encode()).hexdigest()
if len(records) != 45 or len(sources) != 45:
    raise SystemExit("zstd production closure changed")
if digest != "b958ac0c7b62e90253c92959748cf1b577f0292ccc4be6cb1058dcb215f6de8c":
    raise SystemExit("zstd production closure digest changed")
output.write_text("".join(f"{source}\n" for source in sources))
c_output.write_text("".join(f"{source}\n" for source in sources if source.suffix == ".c"))
PY
    cp "$database" "$output/compile_commands.json"

    cppcheck --enable=warning,style,performance,portability \
      --inline-suppr --suppress=missingIncludeSystem \
      --template="{file}:{line}:{column}: {severity}: {id}: {message}" \
      --project="$database" >"$output/cppcheck.log" 2>&1

    cd "$source"
    make -j"$(nproc)" zstd-release CC=gcc \
      CFLAGS="-O0 -g -fanalyzer -Wall -Wextra -fno-omit-frame-pointer" \
      $feature_flags >"$output/gcc-analyzer.log" 2>&1

    if run-clang-tidy-18 -p "$output" \
        -checks="clang-analyzer-*,bugprone-*,performance-*,portability-*" \
        -header-filter="^/rustbox-zstd/source-clang/(lib|programs)/" \
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

    if xargs -n1 sparse \
        -I/rustbox-zstd/source-clang/lib \
        -I/rustbox-zstd/source-clang/lib/common \
        -I/rustbox-zstd/source-clang/lib/compress \
        -I/rustbox-zstd/source-clang/lib/decompress \
        -I/rustbox-zstd/source-clang/lib/dictBuilder \
        -I/rustbox-zstd/source-clang/lib/legacy \
        -I/rustbox-zstd/source-clang/programs \
        -I/work/tools/sparse-compat -DZSTD_MULTITHREAD -pthread \
        <"$output/c-sources.list" >"$output/sparse.log" 2>&1
    then
      sparse_status=0
    else
      sparse_status=$?
    fi
    printf "%s\n" "$sparse_status" >"$output/sparse.status"
  '
