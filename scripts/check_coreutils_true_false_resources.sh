#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
exec "$root/scripts/run_tool.sh" sh -eu -c '
  binary=/rustbox-coreutils/canonical-clang-compdb/src/coreutils-rust-true-false
  for applet in true false; do
    case "$applet" in true) expected=0 ;; false) expected=1 ;; esac
    for option in none --help --version; do
      args="--coreutils-prog=$applet"
      test "$option" = none || args="$args $option"
      log="/tmp/valgrind-$applet-$option.log"
      set +e
      valgrind --quiet --leak-check=full \
        --show-leak-kinds=definite,indirect \
        --errors-for-leak-kinds=definite,indirect \
        --error-exitcode=99 --log-file="$log" \
        "$binary" $args >/dev/null
      status=$?
      set -e
      if test "$status" != "$expected"; then
        cat "$log"
        exit 1
      fi
      if grep -Eq \
        "definitely lost: [1-9]|indirectly lost: [1-9]|ERROR SUMMARY: [1-9]" \
        "$log"; then
        cat "$log"
        exit 1
      fi
    done
  done
  echo "valgrind: 6 true/false cases clean"
'
