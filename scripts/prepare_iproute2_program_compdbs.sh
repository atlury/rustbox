#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-iproute2:2026-11-24 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    analysis=/work/work/analysis/iproute2-7.3.0
    build=/rustbox-iproute2/normalized-clang-18

    # The tc lexer C file is an intermediate and GNU make removes it after the
    # full build.  Recreate it as an explicit target so its exact generic tc
    # compile action can be derived from the captured Clang database.
    make -C "$build" V=1 SHARED_LIBS=n CC=clang-18 HOSTCC=clang-18 \
      --eval="rustbox-generated-source: ; \$(MAKE) -C tc emp_ematch.lex.c" \
      rustbox-generated-source >/dev/null
    python3 -B /work/scripts/prepare_iproute2_program_compdb.py \
      --database "$analysis/normalized/clang-18-compile-commands.json" \
      --maps-directory "$analysis/program-closures/maps" \
      --output-directory "$analysis/program-closures/engines"
    chmod -R a+rwX "$analysis/program-closures/engines"
  '
