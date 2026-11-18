#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
"$root/scripts/provision_coreutils_source.sh"
exec "$root/scripts/run_tool.sh" sh -eu -c '
  state=work/upstream/.state/coreutils.json
  test -f "$state"
  python3 -c '\''import json; assert json.load(open("work/upstream/.state/coreutils.json"))["signature_verified"] is True'\''
  source=/rustbox-source/coreutils-9.12
  build=/rustbox-coreutils/oracle-readonly
  test "$(cat /rustbox-source/archive.sha256)" = \
    a480198559733e9b3da999e90543ac6f888a2caa544d8d664c5a1f17e528e210
  diff -qr work/upstream/coreutils-9.12 "$source"
  mkdir -p "$build"
  cd "$build"
  if test ! -f Makefile; then
    FORCE_UNSAFE_CONFIGURE=1 CC=gcc CFLAGS="-O2 -g" \
      "$source/configure" \
      --enable-install-program=arch,hostname,kill,uptime \
      --enable-single-binary=symlinks
  fi
  make -j"$(nproc)"
  # Automake calls the internal target ginstall, while GNU installs and
  # dispatches the public argv[0] spelling as install.
  ln -sf coreutils src/install
  python3 - <<'\''PY'\''
import json
from pathlib import Path

inventory = json.loads(Path("/work/upstream/applets.json").read_text())
expected = set(inventory["upstreams"]["coreutils"])
actual = {path.name for path in Path("src").iterdir() if path.is_symlink()}
actual.discard("ginstall")
if actual != expected:
    raise SystemExit(f"applet mismatch: missing={sorted(expected-actual)} extra={sorted(actual-expected)}")
print(f"coreutils oracle: all {len(actual)} applet links present")
PY
'
