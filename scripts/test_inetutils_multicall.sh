#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
exec "$root/scripts/run_multicall_tool.sh" sh -eu -c '
    canonical=/rustbox-inetutils/normalized-gcc
    rustbox=/rustbox-coreutils/canonical-clang-no-security-compdb/src/rustbox
    evidence=/work/work/analysis/inetutils-2.8/multicall
    python3 /work/tests/inetutils-multicall-differential.py \
      --canonical-root "$canonical" --rustbox "$rustbox" \
      --output "$evidence/differential.json"
    for name in dnsdomainname ftp ftpd hostname ifconfig inetd logger ping ping6 \
      rcp rexec rexecd rlogin rlogind rsh rshd syslogd talk talkd telnet telnetd \
      tftp tftpd traceroute uucpd whois; do
      dispatch=$name
      case "$name" in
        hostname|logger) dispatch=inetutils-$name ;;
      esac
      valgrind --leak-check=full --show-leak-kinds=all \
        --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
        --log-file="$evidence/valgrind-$name.log" \
        "$rustbox" "$dispatch" --version >"$evidence/valgrind-$name.out"
      grep -q "ERROR SUMMARY: 0 errors" "$evidence/valgrind-$name.log"
      if ! grep -q "All heap blocks were freed -- no leaks are possible" \
          "$evidence/valgrind-$name.log"; then
        grep -q "definitely lost: 0 bytes in 0 blocks" "$evidence/valgrind-$name.log"
        grep -q "indirectly lost: 0 bytes in 0 blocks" "$evidence/valgrind-$name.log"
        grep -q "possibly lost: 0 bytes in 0 blocks" "$evidence/valgrind-$name.log"
      fi
    done
    chmod -R a+rwX "$evidence"
  '
