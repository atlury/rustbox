#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

test "$#" -eq 1 || { echo "usage: $0 BATCH" >&2; exit 2; }
batch=$1
test "$batch" = util-linux-small-01 || { echo "unknown batch: $batch" >&2; exit 2; }

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
exec "$root/scripts/run_tool.sh" sh -eu -c '
  source=/rustbox-util-linux-source/util-linux-2.42.4
  build=/rustbox-util-linux/canonical-clang-compdb
  stable=/work/work/analysis/util-linux-2.42.4/translations/c2rust-0.22.1/util-linux-small-01-stable
  hybrid="$build/rustbox-util-linux-small-01"
  test -x "$hybrid"
  python3 /work/tests/util-linux-small-01-differential.py \
    --canonical-directory "$build" \
    --hybrid "$hybrid" \
    --output "$stable/differential.json"

  cd "$build"
  make -j"$(nproc)" test_md5
  chmod -R a+rwX "$build"
  getent passwd rustbox-test >/dev/null || useradd -m rustbox-test
  export TS_CMD_LINE="$build/rustbox-small-01/line"
  export TS_CMD_SETPGID="$build/rustbox-small-01/setpgid"
  export TS_CMD_EXCH="$build/rustbox-small-01/exch"
  export TS_CMD_SETSID="$build/rustbox-small-01/setsid"
  export TS_CMD_CHOOM="$build/rustbox-small-01/choom"
  export TS_CMD_FADVISE="$build/rustbox-small-01/fadvise"
  export TS_CMD_COLRM="$build/rustbox-small-01/colrm"
  export TS_CMD_MCOOKIE="$build/rustbox-small-01/mcookie"
  export TS_CMD_REV="$build/rustbox-small-01/rev"
  su -m -s /bin/bash rustbox-test -c \
    "cd $build && $source/tests/run.sh --srcdir=$source --builddir=$build line setpgid exch setsid choom fadvise colrm mcookie rev" \
    | tee "$stable/upstream-targeted.log"
  grep -q "All 9 tests PASSED" "$stable/upstream-targeted.log"
'
