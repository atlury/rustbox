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
    for name in rcp rlogin rsh; do
      make -C "$build/src" V=1 -W "$source/src/$name.c" \
        LDFLAGS="-Wl,-Map=$output/$name.map" "$name" \
        >"$output/$name-link.log" 2>&1
    done
    make -C "$build/ftp" V=1 -W "$source/ftp/main.c" \
      LDFLAGS="-Wl,-Map=$output/ftp.map" ftp \
      >"$output/ftp-link.log" 2>&1
    make -C "$build/talk" V=1 -W "$source/talk/talk.c" \
      LDFLAGS="-Wl,-Map=$output/talk.map" talk \
      >"$output/talk-link.log" 2>&1
    make -C "$build/telnet" V=1 -W "$source/telnet/main.c" \
      LDFLAGS="-Wl,-Map=$output/telnet.map" telnet \
      >"$output/telnet-link.log" 2>&1
    for name in inetd rexecd rlogind rshd syslogd tftpd uucpd; do
      make -C "$build/src" V=1 -W "$source/src/$name.c" \
        LDFLAGS="-Wl,-Map=$output/$name.map" "$name" \
        >"$output/$name-link.log" 2>&1
    done
    make -C "$build/ftpd" V=1 -W "$source/ftpd/ftpd.c" \
      LDFLAGS="-Wl,-Map=$output/ftpd.map" ftpd \
      >"$output/ftpd-link.log" 2>&1
    make -C "$build/talkd" V=1 -W "$source/talkd/talkd.c" \
      LDFLAGS="-Wl,-Map=$output/talkd.map" talkd \
      >"$output/talkd-link.log" 2>&1
    make -C "$build/telnetd" V=1 -W "$source/telnetd/telnetd.c" \
      LDFLAGS="-Wl,-Map=$output/telnetd.map" telnetd \
      >"$output/telnetd-link.log" 2>&1
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
