#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
mode=${1:-nonroot}
case "$mode" in
  nonroot|root|expensive) ;;
  *) echo "usage: $0 [nonroot|root|expensive]" >&2; exit 2 ;;
esac

exec "$root/scripts/run_tool.sh" sh -eu -c '
  mode=$1
  build=/rustbox-coreutils/oracle-readonly
  cd "$build"
  test -x src/coreutils
  chmod -R a+rwX "$build"
  case "$mode" in
    root)
      make -j"$(nproc)" check < /dev/null
      ;;
    nonroot|expensive)
      getent group rustbox-extra >/dev/null || groupadd rustbox-extra
      getent passwd rustbox-test >/dev/null || useradd -m -G rustbox-extra rustbox-test
      if test "$mode" = expensive; then
        su -s /bin/sh rustbox-test -c \
          '\''cd /rustbox-coreutils/oracle-readonly && make -j"$(nproc)" check RUN_EXPENSIVE_TESTS=yes'\'' \
          < /dev/null
      else
        su -s /bin/sh rustbox-test -c \
          '\''cd /rustbox-coreutils/oracle-readonly && make -j"$(nproc)" check'\'' \
          < /dev/null
      fi
      ;;
  esac
' sh "$mode"
