#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-xz:2026-11-22 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    release=/work/work/upstream/xz-5.8.4
    source=/rustbox-xz/analyzer-source
    output=/work/work/analysis/xz-5.8.4/analyzers
    database=/work/work/analysis/xz-5.8.4/oracle/clang-compile-commands.json
    rm -rf "$source" "$output"
    cp -a "$release" "$source"
    mkdir -p "$output"

    python3 - "$database" "$output/sources.list" <<"PY"
import hashlib,json,sys
from pathlib import Path
database,output=map(Path,sys.argv[1:])
records=json.loads(database.read_text())
root=Path("/rustbox-xz/source-clang")
sources=sorted({Path(record["file"]).resolve() for record in records})
relative=[source.relative_to(root).as_posix() for source in sources]
digest=hashlib.sha256(("\n".join(relative)+"\n").encode()).hexdigest()
if len(records) != 113 or len(sources) != 101:
    raise SystemExit("XZ production closure changed")
if digest != "1d9270fb42e95e59fd9bbc00a583d21d5cf84896cac89b4a5ab429d38cb7f7a2":
    raise SystemExit("XZ production closure digest changed")
output.write_text("".join(f"{source}\n" for source in sources))
PY
    cp "$database" "$output/compile_commands.json"

    cppcheck --enable=warning,style,performance,portability \
      --inline-suppr --suppress=missingIncludeSystem \
      --template="{file}:{line}:{column}: {severity}: {id}: {message}" \
      --project="$database" >"$output/cppcheck.log" 2>&1

    cd "$source"
    ./configure --disable-shared --enable-static --disable-nls CC=gcc \
      CFLAGS="-O0 -g -fanalyzer -Wall -Wextra -fno-omit-frame-pointer" \
      >"$output/gcc-analyzer-configure.log" 2>&1
    make -j"$(nproc)" V=1 >"$output/gcc-analyzer.log" 2>&1

    run-clang-tidy-18 -p "$output" \
      -checks="clang-analyzer-*,bugprone-*,performance-*,portability-*" \
      -header-filter="^/rustbox-xz/source-clang/src/" \
      >"$output/clang-analyzer-tidy.log" 2>&1

    xargs flawfinder --minlevel=1 --quiet <"$output/sources.list" \
      >"$output/flawfinder.log" 2>&1

    if xargs -n1 sparse -I/rustbox-xz/source-clang \
        -I/rustbox-xz/source-clang/src/common \
        -I/rustbox-xz/source-clang/src/liblzma/api \
        -I/rustbox-xz/source-clang/src/liblzma/common \
        -I/rustbox-xz/source-clang/src/liblzma/check \
        -I/rustbox-xz/source-clang/src/liblzma/lz \
        -I/rustbox-xz/source-clang/src/liblzma/lzma \
        -I/rustbox-xz/source-clang/src/liblzma/rangecoder \
        -I/rustbox-xz/source-clang/src/liblzma/delta \
        -I/rustbox-xz/source-clang/src/liblzma/simple \
        -I/work/tools/sparse-compat -DHAVE_CONFIG_H \
        <"$output/sources.list" >"$output/sparse.log" 2>&1
    then
      sparse_status=0
    else
      sparse_status=$?
    fi
    printf "%s\n" "$sparse_status" >"$output/sparse.status"
  '
