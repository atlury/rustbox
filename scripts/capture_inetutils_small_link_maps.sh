#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-inetutils:2026-11-23 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    build=/rustbox-inetutils/normalized-gcc
    source=/rustbox-inetutils/normalized-source
    output=/work/work/analysis/inetutils-2.8/program-closures
    mkdir -p "$output"
    for name in dnsdomainname hostname logger; do
      make -C "$build/src" V=1 -W "$source/src/$name.c" \
        LDFLAGS="-Wl,-Map=$output/$name.map" "$name" \
        >"$output/$name-link.log" 2>&1
    done
    make -C "$build/whois" V=1 -W "$source/whois/whois.c" \
      LDFLAGS="-Wl,-Map=$output/whois.map" whois \
      >"$output/whois-link.log" 2>&1
    chmod -R a+rwX "$output"
  '
