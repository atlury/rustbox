#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

test "$#" -eq 1 || { echo "usage: $0 BATCH" >&2; exit 2; }
batch=$1
case $batch in
  util-linux-small-01) suffix=01; components='line setpgid exch setsid choom fadvise colrm mcookie rev'; count=9 ;;
  util-linux-small-02) suffix=02; components='isosize'; count=1 ;;
  util-linux-small-03) suffix=03; components='swaplabel uuidgen ionice copyfilerange'; count=5 ;;
  util-linux-small-04) suffix=04; components='bits colcrt getino mountpoint waitpid'; count=7 ;;
  *) echo "unknown batch: $batch" >&2; exit 2 ;;
esac

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
exec "$root/scripts/run_tool.sh" sh -eu -c '
  source=/rustbox-util-linux-source/util-linux-2.42.4
  build=/rustbox-util-linux/canonical-clang-compdb
  suffix=$1
  components=$2
  count=$3
  stable="/work/work/analysis/util-linux-2.42.4/translations/c2rust-0.22.1/util-linux-small-$suffix-stable"
  hybrid="$build/rustbox-util-linux-small-$suffix"
  test -x "$hybrid"
  python3 "/work/tests/util-linux-small-$suffix-differential.py" \
    --canonical-directory "$build" \
    --hybrid "$hybrid" \
    --output "$stable/differential.json"

  cd "$build"
  if test "$suffix" = 01; then make -j"$(nproc)" test_md5; fi
  if test "$suffix" = 03; then make -j"$(nproc)" test_sysinfo test_uuid_parser; fi
  if test "$suffix" = 04; then make -j"$(nproc)" test_strerror; fi
  chmod -R a+rwX "$build"
  getent passwd rustbox-test >/dev/null || useradd -m rustbox-test
  if test "$suffix" = 01; then
    export TS_CMD_LINE="$build/rustbox-small-01/line"
    export TS_CMD_SETPGID="$build/rustbox-small-01/setpgid"
    export TS_CMD_EXCH="$build/rustbox-small-01/exch"
    export TS_CMD_SETSID="$build/rustbox-small-01/setsid"
    export TS_CMD_CHOOM="$build/rustbox-small-01/choom"
    export TS_CMD_FADVISE="$build/rustbox-small-01/fadvise"
    export TS_CMD_COLRM="$build/rustbox-small-01/colrm"
    export TS_CMD_MCOOKIE="$build/rustbox-small-01/mcookie"
    export TS_CMD_REV="$build/rustbox-small-01/rev"
  elif test "$suffix" = 02; then
    export TS_CMD_ISOSIZE="$build/rustbox-small-02/isosize"
  elif test "$suffix" = 03; then
    export TS_CMD_SWAPLABEL="$build/rustbox-small-03/swaplabel"
    export TS_CMD_UUIDGEN="$build/rustbox-small-03/uuidgen"
    export TS_CMD_IONICE="$build/rustbox-small-03/ionice"
    export TS_CMD_COPYFILERANGE="$build/rustbox-small-03/copyfilerange"
  else
    export TS_CMD_BITS="$build/rustbox-small-04/bits"
    export TS_CMD_COLCRT="$build/rustbox-small-04/colcrt"
    export TS_CMD_GETINO="$build/rustbox-small-04/getino"
    export TS_CMD_MOUNTPOINT="$build/rustbox-small-04/mountpoint"
    export TS_CMD_WAITPID="$build/rustbox-small-04/waitpid"
  fi
  su -m -s /bin/bash rustbox-test -c \
    "cd $build && $source/tests/run.sh --srcdir=$source --builddir=$build $components" \
    | tee "$stable/upstream-targeted.log"
  grep -q "All $count tests PASSED" "$stable/upstream-targeted.log"
' rustbox-util-test "$suffix" "$components" "$count"
