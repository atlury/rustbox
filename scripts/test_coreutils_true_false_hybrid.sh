#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
mode=${1:-targeted}
case "$mode" in targeted|full) ;; *) echo "usage: $0 [targeted|full]" >&2; exit 2 ;; esac
exec "$root/scripts/run_tool.sh" sh -eu -c '
  mode=$1
  build=/rustbox-coreutils/canonical-clang-compdb
  canonical="$build/src/coreutils"
  hybrid="$build/src/coreutils-rust-true-false"
  output=/work/work/analysis/coreutils-9.12/translations/c2rust-0.22.1/true-false/differential.json
  python3 /work/tests/coreutils_true_false_differential.py \
    --canonical "$canonical" --hybrid "$hybrid" --output "$output"

  cd "$build"
  test "$(readlink src/true)" = coreutils
  test "$(readlink src/false)" = coreutils
  restore () {
    ln -sfn coreutils src/true
    ln -sfn coreutils src/false
  }
  trap restore EXIT HUP INT TERM
  ln -sfn coreutils-rust-true-false src/true
  ln -sfn coreutils-rust-true-false src/false
  chmod -R a+rwX "$build"
  getent group rustbox-extra >/dev/null || groupadd rustbox-extra
  getent passwd rustbox-test >/dev/null || useradd -m -G rustbox-extra rustbox-test
  if test "$mode" = targeted; then
    su -s /bin/sh rustbox-test -c '\''
      cd /rustbox-coreutils/canonical-clang-compdb
      make check-TESTS TESTS="tests/misc/false-status.sh tests/help/help-version.sh tests/help/help-version-getopt.sh"
    '\'' < /dev/null
  else
    set +e
    su -s /bin/sh rustbox-test -c '\''
      cd /rustbox-coreutils/canonical-clang-compdb
      make -j"$(nproc)" check
    '\'' < /dev/null
    status=$?
    set -e
    test "$status" -ne 0
    grep -q "^# TOTAL: 761$" tests/test-suite.log
    grep -q "^# PASS:  628$" tests/test-suite.log
    grep -q "^# SKIP:  132$" tests/test-suite.log
    grep -q "^# FAIL:  0$" tests/test-suite.log
    grep -q "^# ERROR: 1$" tests/test-suite.log
    grep -q "^ERROR: tests/rm/deep-2$" tests/test-suite.log
    echo "full hybrid suite: 628 pass, 132 skip, 0 fail, 1 known VM path setup error"
  fi
' sh "$mode"
