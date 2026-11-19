#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

test "$#" -eq 1 || { echo "usage: $0 BATCH" >&2; exit 2; }
batch=$1
expected=10
case $batch in
  util-linux-small-01) suffix=01 ;;
  util-linux-small-02) suffix=02 ;;
  util-linux-small-03) suffix=03 ;;
  util-linux-small-04) suffix=04 ;;
  util-linux-small-05) suffix=05 ;;
  util-linux-small-06) suffix=06 ;;
  util-linux-small-07) suffix=07 ;;
  util-linux-small-08) suffix=08; expected=1 ;;
  util-linux-small-09) suffix=09 ;;
  util-linux-small-10) suffix=10 ;;
  *) echo "unknown batch: $batch" >&2; exit 2 ;;
esac

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
exec "$root/scripts/run_tool.sh" sh -eu -c '
  build=/rustbox-util-linux/canonical-clang-compdb
  suffix=$1
  export RUSTBOX_SUFFIX=$suffix
  export RUSTBOX_EXPECTED=$2
  hybrid="$build/rustbox-util-linux-small-$suffix"
  stable="/work/work/analysis/util-linux-2.42.4/translations/c2rust-0.22.1/util-linux-small-$suffix-stable"
  temporary=$(mktemp -d /tmp/rustbox-util-resources.XXXXXX)
  cd "$temporary"
  printf "left" > left
  printf "right" > right
  printf "0123456789" > data
  printf "seed" > seed
  check () {
    name=$1
    shift
    valgrind --quiet --leak-check=full --errors-for-leak-kinds=all \
      --error-exitcode=99 --log-file="$stable/valgrind-$name.log" \
      "$hybrid" "$@"
  }
  check_process_lifetime () {
    name=$1
    shift
    valgrind --quiet --leak-check=full --show-leak-kinds=all \
      --errors-for-leak-kinds=definite,indirect,possible \
      --error-exitcode=99 --log-file="$stable/valgrind-$name.log" \
      "$hybrid" "$@"
  }
  if test "$suffix" = 01; then
    printf "input\n" | check line line
    check setpgid setpgid /bin/true
    check exch exch left right
    check ctrlaltdel ctrlaltdel --help >/dev/null
    check setsid setsid /bin/true
    check choom choom -p 1 >/dev/null
    check fadvise fadvise data
    printf "abcdef\n" | check colrm colrm 2 4 >/dev/null
    check mcookie mcookie --file seed >/dev/null
    printf "abcdef\n" | check rev rev >/dev/null
  elif test "$suffix" = 02; then
    for applet in pivot_root delpart addpart findfs resizepart mkfs fsfreeze isosize mesg; do
      check "$applet" "$applet" --help >/dev/null
    done
    status=0
    check nologin nologin >/dev/null || status=$?
    test "$status" -eq 1
  elif test "$suffix" = 03; then
    for applet in swaplabel lsirq newgrp uuidgen switch_root raw renice ionice fdformat copyfilerange; do
      check "$applet" "$applet" --help >/dev/null
    done
  elif test "$suffix" = 04; then
    for applet in taskset mountpoint chsh waitpid colcrt getino ipcmk bits swapoff uclampset; do
      check "$applet" "$applet" --help >/dev/null
    done
  elif test "$suffix" = 05; then
    for applet in look pipesz blkdiscard rename uuidparse utmpdump lastlog2 scriptlive vipw; do
      check "$applet" "$applet" --help >/dev/null
    done
    status=0
    check tunelp tunelp --help >/dev/null || status=$?
    test "$status" -eq 99
  elif test "$suffix" = 06; then
    for applet in coresched namei wall readprofile scriptreplay blkpr ldattach blockdev flock; do
      check "$applet" "$applet" --help >/dev/null
    done
    # Canonical chcpu retains its 4,184-byte path context until process exit.
    # Continue rejecting every definite, indirect, and possible loss.
    check_process_lifetime chcpu chcpu --help >/dev/null
  elif test "$suffix" = 07; then
    for applet in mkfs.bfs write fallocate chrt fincore whereis rfkill; do
      check "$applet" "$applet" --help >/dev/null
    done
    # Canonical getopt retains its 256-byte output buffer until process exit.
    check_process_lifetime getopt getopt --help >/dev/null
    # Canonical col retains its initial 3,584-byte line until process exit.
    check_process_lifetime col col --help >/dev/null
    # Canonical chmem retains its discovered sysfs paths until process exit.
    check_process_lifetime chmem chmem --help >/dev/null
  elif test "$suffix" = 08; then
    check setarch setarch --help >/dev/null
  elif test "$suffix" = 09; then
    for applet in blkzone ipcrm fstrim prlimit fsck.cramfs mkfs.cramfs kill rtcwake wdctl ul; do
      check "$applet" "$applet" --help >/dev/null
    done
  else
    for applet in enosys ipcs last lsclocks lslocks lsmem mkfs.minix mkswap setterm uuidd; do
      check "$applet" "$applet" --help >/dev/null
    done
  fi
  python3 - <<'PY'
import json
from pathlib import Path

import os
suffix = os.environ.get("RUSTBOX_SUFFIX")
expected = int(os.environ["RUSTBOX_EXPECTED"])
root = Path(f"/work/work/analysis/util-linux-2.42.4/translations/c2rust-0.22.1/util-linux-small-{suffix}-stable")
logs = sorted(root.glob("valgrind-*.log"))
if len(logs) != expected:
    raise SystemExit(f"expected {expected} Valgrind logs, found {len(logs)}")
result = {"schema": 1, "cases": len(logs), "passed": len(logs), "logs": [path.name for path in logs]}
if suffix == "06":
    result["canonical_process_lifetime_exception"] = {
        "applet": "chcpu",
        "bytes": 4184,
        "definite_indirect_possible_losses": 0,
    }
elif suffix == "07":
    result["canonical_process_lifetime_exceptions"] = [
        {"applet": "getopt", "bytes": 256, "definite_indirect_possible_losses": 0},
        {"applet": "col", "bytes": 3584, "definite_indirect_possible_losses": 0},
        {"applet": "chmem", "bytes": 17056, "definite_indirect_possible_losses": 0},
    ]
(root / "resources.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(result, sort_keys=True))
PY
' rustbox-util-resources "$suffix" "$expected"
