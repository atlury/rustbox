#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-gzip:2026-11-21 \
  exec "$root/scripts/run_tool.sh" python3 /work/scripts/summarize_gzip_oracle.py \
    --repository /work \
    --gcc-install /rustbox-gzip/install-gcc/usr/bin \
    --clang-install /rustbox-gzip/install-clang/usr/bin \
    --output /work/evidence/gzip-1.14-oracle.json
