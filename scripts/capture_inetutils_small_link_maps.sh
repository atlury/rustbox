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
    for name in rexec tftp traceroute; do
      make -C "$build/src" V=1 -W "$source/src/$name.c" \
        LDFLAGS="-Wl,-Map=$output/$name.map" "$name" \
        >"$output/$name-link.log" 2>&1
    done
    make -C "$build/ifconfig" V=1 -W "$source/ifconfig/ifconfig.c" \
      LDFLAGS="-Wl,-Map=$output/ifconfig.map" ifconfig \
      >"$output/ifconfig-link.log" 2>&1
    for name in ping ping6; do
      make -C "$build/ping" V=1 -W "$source/ping/$name.c" \
        LDFLAGS="-Wl,-Map=$output/$name.map" "$name" \
        >"$output/$name-link.log" 2>&1
    done
    make -C "$build/whois" V=1 -W "$source/whois/whois.c" \
      LDFLAGS="-Wl,-Map=$output/whois.map" whois \
      >"$output/whois-link.log" 2>&1
    chmod -R a+rwX "$output"
  '
