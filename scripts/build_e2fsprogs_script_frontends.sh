#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
exec docker run --rm --platform linux/amd64 \
  --volume "$root:/work" --workdir /work rustbox-e2fsprogs:2026-11-24 \
  sh -eu -c '
    source=/work/work/upstream/e2fsprogs-1.47.4
    output=/work/work/analysis/e2fsprogs-1.47.4/script-frontends
    rm -rf "$output"
    mkdir -p "$output"
    python3 -B /work/scripts/generate_e2fsprogs_script_templates.py \
      --source "$source" --output "$output/templates.c"
    for compiler in gcc clang-18; do
      directory=$output/$compiler
      mkdir -p "$directory"
      "$compiler" -std=c11 -Os -Wall -Wextra -Werror \
        -ffunction-sections -fdata-sections \
        /work/bridges/e2fsprogs_script_frontends.c "$output/templates.c" \
        -Wl,--gc-sections -o "$directory/e2fsprogs-script-frontends"
      for name in e2scrub e2scrub_all compile_et mk_cmds; do
        ln -s e2fsprogs-script-frontends "$directory/$name"
      done
    done
    gcc -std=c11 -Os -Wall -Wextra -Werror \
      -ffunction-sections -fdata-sections -DRUSTBOX_MULTICALL \
      -c /work/bridges/e2fsprogs_script_frontends.c \
      -o "$output/e2fsprogs-script-frontends.o"
    gcc -std=c11 -Os -Wall -Wextra -Werror \
      -ffunction-sections -fdata-sections \
      -c "$output/templates.c" -o "$output/e2fsprogs-script-templates.o"
    chmod -R a+rwX "$output"
  '
