#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
"$root/scripts/provision_util_linux_source.sh"
mkdir -p "$root/work/analysis/util-linux-2.42.4/canonical-gcc"

exec "$root/scripts/run_tool.sh" sh -eu -c '
  source=/rustbox-util-linux-source/util-linux-2.42.4
  build=/rustbox-util-linux/canonical-gcc-compdb
  output=/work/work/analysis/util-linux-2.42.4/canonical-gcc
  mkdir -p "$build" "$output"
  cd "$build"
  if test ! -f Makefile; then
    CC=gcc CXX=g++ CFLAGS="-O1 -g" CPPFLAGS="-I/work/compat/util-linux" \
      "$source/configure" \
      --without-selinux --without-systemd --without-audit --without-udev \
      --without-python --disable-pylibmount --disable-pam-lastlog2 \
      --enable-liblastlog2 --enable-setpriv --enable-raw \
      --enable-fdformat --enable-line --enable-vipw --enable-newgrp \
      --enable-pg --enable-write --enable-tunelp
  fi
  if test ! -s compile_commands.json; then
    bear --output compile_commands.json -- make -j"$(nproc)"
  else
    make -j"$(nproc)"
  fi
  python3 /work/scripts/summarize_compdb.py \
    --database compile_commands.json \
    --source-root "$source" \
    --build-root "$build" \
    --compiler-family gcc \
    --output "$output/summary.json"
  cp compile_commands.json "$output/compile_commands.json"
'
