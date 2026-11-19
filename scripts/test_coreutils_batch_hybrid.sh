#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

test "$#" -ge 1 && test "$#" -le 2 || {
  echo "usage: $0 BATCH [targeted|full]" >&2
  exit 2
}
batch=$1
mode=${2:-targeted}
case $batch in
  *[!A-Za-z0-9_-]*|'') exit 2 ;;
esac
case $mode in
  targeted|full) ;;
  *) exit 2 ;;
esac

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
manifest="$root/batches/$batch.json"
test -s "$manifest" || { echo "unknown batch: $batch" >&2; exit 2; }
applets=$(python3 -c 'import json,sys; print(" ".join(json.load(open(sys.argv[1]))["applets"]))' "$manifest")
tests=$(python3 -c 'import json,sys; print(" ".join(json.load(open(sys.argv[1]))["upstream_tests"]))' "$manifest")
harness=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["differential_harness"])' "$manifest")
canonical_build=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("canonical_build", "canonical-clang-compdb"))' "$manifest")
case $canonical_build in
  *[!A-Za-z0-9_-]*|'') echo "unsafe canonical build name" >&2; exit 2 ;;
esac

exec "$root/scripts/run_tool.sh" sh -eu -c '
  batch=$1
  mode=$2
  applets=$3
  tests=$4
  harness=$5
  build="/rustbox-coreutils/$6"
  canonical="$build/src/coreutils"
  hybrid="$build/src/coreutils-rust-$batch"
  output="/work/work/analysis/coreutils-9.12/translations/c2rust-0.22.1/$batch-stable/differential.json"
  test -x "$canonical"
  test -x "$hybrid"
  test -f "/work/tests/$harness"
  python3 "/work/tests/$harness" \
    --canonical "$canonical" --hybrid "$hybrid" --output "$output"

  cd "$build"
  for applet in $applets; do
    test "$(readlink "src/$applet")" = coreutils
  done
  restore () {
    for applet in $applets; do
      ln -sfn coreutils "src/$applet"
    done
  }
  trap restore EXIT HUP INT TERM
  for applet in $applets; do
    ln -sfn "coreutils-rust-$batch" "src/$applet"
  done

  chmod -R a+rwX "$build"
  getent group rustbox-extra >/dev/null || groupadd rustbox-extra
  getent passwd rustbox-test >/dev/null || useradd -m -G rustbox-extra rustbox-test
  if test "$mode" = targeted; then
    su -s /bin/sh rustbox-test -c "
      cd $build
      make check-TESTS TESTS=\"$tests\"
    " < /dev/null
    python3 /work/scripts/summarize_testsuite_log.py \
      --log tests/test-suite.log \
      --suite targeted \
      --output "/work/work/analysis/coreutils-9.12/translations/c2rust-0.22.1/$batch-stable/upstream-targeted.json"
  else
    set +e
    su -s /bin/sh rustbox-test -c "
      cd $build
      make -j\"\$(nproc)\" check
    " < /dev/null
    status=$?
    set -e
    test "$status" -ne 0
    grep -q "^# TOTAL: 761$" tests/test-suite.log
    grep -q "^# PASS:  628$" tests/test-suite.log
    grep -q "^# SKIP:  132$" tests/test-suite.log
    grep -q "^# FAIL:  0$" tests/test-suite.log
    grep -q "^# ERROR: 1$" tests/test-suite.log
    grep -q "^ERROR: tests/rm/deep-2$" tests/test-suite.log
    python3 /work/scripts/summarize_testsuite_log.py \
      --log tests/test-suite.log \
      --suite full \
      --output "/work/work/analysis/coreutils-9.12/translations/c2rust-0.22.1/$batch-stable/upstream-full.json"
    echo "full hybrid suite: 628 pass, 132 skip, 0 fail, 1 known VM path setup error"
  fi
' rustbox-batch-test "$batch" "$mode" "$applets" "$tests" "$harness" "$canonical_build"
