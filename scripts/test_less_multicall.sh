#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
exec "$root/scripts/run_multicall_tool.sh" sh -eu -c '
    rustbox=/rustbox-coreutils/canonical-clang-no-security-compdb/src/rustbox
    oracle=/work/work/analysis/less-710/normalized/gcc
    dispatch=/rustbox-less/multicall-dispatch
    analysis=/work/work/analysis/less-710/multicall
    rm -rf "$dispatch" "$analysis"
    mkdir -p "$dispatch" "$analysis"
    ln -s "$rustbox" "$dispatch/less"
    ln -s "$rustbox" "$dispatch/lessecho"
    python3 /work/tests/less-oracle-differential.py \
      --gcc-directory "$oracle" --clang-directory "$dispatch" \
      --output "$analysis/differential.json"

    printf "alpha beta gamma\n%.0s" $(seq 1 1024) >"$analysis/input"
    for applet in less lessecho; do
      if test "$applet" = less; then args="$analysis/input"; else args="-a alpha-beta"; fi
      LESSHISTFILE=- TERM=xterm valgrind --leak-check=full --show-leak-kinds=all \
        --errors-for-leak-kinds=definite,indirect --error-exitcode=99 \
        --log-file="$analysis/valgrind-$applet.log" \
        "$dispatch/$applet" $args >"$analysis/$applet.out"
      grep -q "ERROR SUMMARY: 0 errors" "$analysis/valgrind-$applet.log"
      if grep -q "LEAK SUMMARY" "$analysis/valgrind-$applet.log"; then
        grep -q "definitely lost: 0 bytes" "$analysis/valgrind-$applet.log"
        grep -q "indirectly lost: 0 bytes" "$analysis/valgrind-$applet.log"
      else
        grep -q "All heap blocks were freed -- no leaks are possible" "$analysis/valgrind-$applet.log"
      fi
    done
  '
