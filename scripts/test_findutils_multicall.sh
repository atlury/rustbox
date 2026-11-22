#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-file:2026-11-20 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    stage=/rustbox-findutils/multicall
    report=/work/work/analysis/findutils-4.10.0/multicall
    binary=/rustbox-coreutils/canonical-clang-no-security-compdb/src/rustbox
    rm -rf "$stage" "$report"
    mkdir -p "$stage/find" "$stage/xargs" "$stage/locate" "$report"
    ln -s "$binary" "$stage/find/find"
    ln -s "$binary" "$stage/xargs/xargs"
    ln -s "$binary" "$stage/locate/locate"
    # The oracle harness creates its fixture database by invoking the private
    # libexec encoder directly.  updatedb itself exercises the linked encoder.
    ln -s /rustbox-findutils/hybrid/locate/frcode "$stage/locate/frcode"
    ln -s "$binary" "$stage/locate/updatedb"
    python3 /work/tests/findutils-oracle-differential.py \
      --gcc-build /rustbox-findutils/hybrid \
      --clang-build "$stage" \
      --output "$report/differential.json"
    for item in find/find xargs/xargs locate/locate locate/updatedb; do
      name=$(basename "$item")
      valgrind --leak-check=full --show-leak-kinds=all \
        --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
        --log-file="$report/valgrind-$name.log" \
        "$stage/$item" --version \
        </dev/null >"$report/valgrind-$name.out" 2>&1
      grep -q "ERROR SUMMARY: 0 errors" "$report/valgrind-$name.log"
    done
  '
