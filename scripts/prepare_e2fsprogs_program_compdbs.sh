#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
exec docker run --rm --platform linux/amd64 \
  --volume "$root:/work" \
  --volume rustbox-e2fsprogs-1.47.4:/rustbox-e2fsprogs \
  --workdir /work --entrypoint sh rustbox-e2fsprogs:2026-11-24 -eu -c '
    analysis=/work/work/analysis/e2fsprogs-1.47.4
    python3 -B /work/scripts/prepare_e2fsprogs_program_compdb.py \
      --database "$analysis/normalization/clang-18-compile-commands.json" \
      --maps-directory "$analysis/program-closures/maps" \
      --output-directory "$analysis/program-closures/engines"
    chmod -R a+rwX "$analysis/program-closures/engines"
  '
