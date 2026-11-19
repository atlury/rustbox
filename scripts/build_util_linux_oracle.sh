#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
"$root/scripts/provision_util_linux_source.sh"
exec "$root/scripts/run_tool.sh" sh -eu -c '
  test -f work/upstream/.state/util-linux.json
  python3 -c '\''import json; assert json.load(open("work/upstream/.state/util-linux.json"))["signature_verified"] is True'\''
  source=/rustbox-util-linux-source/util-linux-2.42.4
  build=/rustbox-util-linux/oracle-gcc-full
  test "$(cat /rustbox-util-linux-source/archive.sha256)" = \
    fbd62a100ab7bb8746ba0661255c3c48185b1e9021507c624da01fbc696330ec
  diff -qr work/upstream/util-linux-2.42.4 "$source"
  mkdir -p "$build"
  cd "$build"
  if test ! -f Makefile; then
    CC=gcc CFLAGS="-O2 -g" CPPFLAGS="-I/work/compat/util-linux" \
      "$source/configure" \
      --without-selinux \
      --without-systemd \
      --without-audit \
      --without-udev \
      --without-python \
      --disable-pylibmount \
      --disable-pam-lastlog2 \
      --enable-liblastlog2 \
      --enable-setpriv \
      --enable-raw \
      --enable-fdformat \
      --enable-line \
      --enable-vipw \
      --enable-newgrp \
      --enable-pg \
      --enable-write \
      --enable-tunelp
  fi
  make -j"$(nproc)"
  for alias in i386 ia64 linux32 linux64 mips mips32 mips64 parisc parisc32 \
               parisc64 ppc ppc32 ppc64 s390 s390x sparc sparc32 sparc32bash \
               sparc64 uname26 x86_64; do
    ln -sfn setarch "$alias"
  done
  ln -sfn last lastb
  ln -sfn vipw vigr
  find . -type f -perm /111 -printf "%f\n" | sort -u > rustbox-built-executables.txt
  python3 - <<'PY'
import json
import os
from pathlib import Path

expected = set(json.loads(Path("/work/upstream/applets.json").read_text())
               ["upstreams"]["util-linux"])
actual = {
    path.name for path in Path(".").rglob("*")
    if path.is_symlink() or (path.is_file() and os.access(path, os.X_OK))
}
missing = expected - actual
if missing:
    raise SystemExit(f"util-linux oracle missing applets: {sorted(missing)}")
print(f"util-linux oracle: all {len(expected)} applet names present")
PY
  printf "util-linux oracle executables: %s unique names\n" \
    "$(wc -l < rustbox-built-executables.txt)"
'
