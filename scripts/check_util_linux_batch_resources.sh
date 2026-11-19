#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

test "$#" -eq 1 || { echo "usage: $0 BATCH" >&2; exit 2; }
batch=$1
case $batch in
  util-linux-small-01) suffix=01 ;;
  util-linux-small-02) suffix=02 ;;
  *) echo "unknown batch: $batch" >&2; exit 2 ;;
esac

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
exec "$root/scripts/run_tool.sh" sh -eu -c '
  build=/rustbox-util-linux/canonical-clang-compdb
  suffix=$1
  export RUSTBOX_SUFFIX=$suffix
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
  else
    for applet in pivot_root delpart addpart findfs resizepart mkfs fsfreeze isosize mesg; do
      check "$applet" "$applet" --help >/dev/null
    done
    status=0
    check nologin nologin >/dev/null || status=$?
    test "$status" -eq 1
  fi
  python3 - <<'PY'
import json
from pathlib import Path

import os
suffix = os.environ.get("RUSTBOX_SUFFIX")
root = Path(f"/work/work/analysis/util-linux-2.42.4/translations/c2rust-0.22.1/util-linux-small-{suffix}-stable")
logs = sorted(root.glob("valgrind-*.log"))
if len(logs) != 10:
    raise SystemExit(f"expected 10 Valgrind logs, found {len(logs)}")
result = {"schema": 1, "cases": len(logs), "passed": len(logs), "logs": [path.name for path in logs]}
(root / "resources.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(result, sort_keys=True))
PY
' rustbox-util-resources "$suffix"
