#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
base="$root/work/analysis/inetutils-2.8/program-translations"
database=/work/work/analysis/inetutils-2.8/normalized/clang-compile-commands.json

for item in \
  rexec:src/rexec.c \
  tftp:src/tftp.c \
  traceroute:src/traceroute.c \
  ifconfig:ifconfig/ifconfig.c \
  ping:ping/ping.c \
  ping6:ping/ping6.c
do
  name=${item%%:*}
  source=${item#*:}
  program="$base/$name"
  rm -rf "$program"
  mkdir -p "$program"
  RUSTBOX_TOOL_IMAGE=rustbox-inetutils:2026-11-23 \
    "$root/scripts/run_tool.sh" python3 -B \
      /work/scripts/prepare_inetutils_program_compdb.py \
      --database "$database" \
      --map "/work/work/analysis/inetutils-2.8/program-closures/$name.map" \
      --main-source "$source" \
      --output "/work/work/analysis/inetutils-2.8/program-translations/$name/compile_commands.json" \
      --manifest "/work/work/analysis/inetutils-2.8/program-translations/$name/closure.json"
  RUSTBOX_TOOL_IMAGE=rustbox-inetutils:2026-11-23 \
    "$root/scripts/run_tool.sh" sh -eu -c "
      RAYON_NUM_THREADS=1 c2rust transpile \
        /work/work/analysis/inetutils-2.8/program-translations/$name/compile_commands.json \
        --output-dir /work/work/analysis/inetutils-2.8/program-translations/$name/${name}-audit \
        --emit-build-files --fail-on-error --disable-rustfmt \
        --overwrite-existing --preserve-unused-functions
    "
  python3 -B "$root/scripts/modernize_c2rust_output.py" \
    --input "$program/${name}-audit" --output "$program/${name}-stable"
done
