#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
exec "$root/scripts/run_multicall_tool.sh" sh -eu -c '
    rustbox=/rustbox-coreutils/canonical-clang-no-security-compdb/src/rustbox
    canonical=/work/work/analysis/ncurses-6.6/normalized/gcc-root
    output=/work/work/analysis/ncurses-6.6/multicall
    dispatch=$output/dispatch-root
    rm -rf "$output"
    mkdir -p "$dispatch/usr/bin" "$dispatch/usr/share"

    for name in captoinfo clear infocmp infotocap tabs tic toe tput tset reset ncursesw6-config; do
      ln -s "$rustbox" "$dispatch/usr/bin/$name"
    done
    cp -a "$canonical/usr/share/terminfo" "$dispatch/usr/share/terminfo"

    python3 /work/tests/ncurses-oracle-differential.py \
      --gcc-root "$canonical" --clang-root "$dispatch" \
      --output "$output/differential.json"
    python3 /work/tests/ncurses-config-frontend.py \
      --canonical "$canonical/usr/bin/ncursesw6-config" \
      --native "$dispatch/usr/bin/ncursesw6-config" \
      --output "$output/ncursesw6-config-differential.json"

    for name in captoinfo clear infocmp infotocap tabs tic toe tput tset reset ncursesw6-config; do
      option=-V
      [ "$name" != ncursesw6-config ] || option=--version
      TERM=xterm TERMINFO="$dispatch/usr/share/terminfo" \
        valgrind --leak-check=full --show-leak-kinds=all \
          --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
          --log-file="$output/valgrind-$name.log" \
          "$rustbox" "$name" "$option" \
          >"$output/valgrind-$name.out" 2>&1
      grep -q "ERROR SUMMARY: 0 errors" "$output/valgrind-$name.log"
      grep -Eq "All heap blocks were freed|definitely lost: 0 bytes" \
        "$output/valgrind-$name.log"
      grep -Eq "All heap blocks were freed|indirectly lost: 0 bytes" \
        "$output/valgrind-$name.log"
      grep -Eq "All heap blocks were freed|possibly lost: 0 bytes" \
        "$output/valgrind-$name.log"
    done
  '
