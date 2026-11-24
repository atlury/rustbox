#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-shadow:2026-11-24 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    output=/work/work/analysis/shadow-4.20.4/oracle
    programs="chage chfn chgpasswd chpasswd chsh faillog getsubids gpasswd groupadd groupdel groupmod grpck grpconv grpunconv lastlog login newgidmap newgrp newuidmap newusers nologin passwd pwck pwconv pwunconv su useradd userdel usermod vipw sg vigr"
    export LC_ALL=C LANG=C TZ=UTC
    set +e
    for program in $programs; do
      timeout --signal=TERM --kill-after=5s 30s \
        valgrind --leak-check=full --show-leak-kinds=all \
          --errors-for-leak-kinds=definite,indirect,possible \
          --error-exitcode=99 /rustbox-shadow/programs-gcc/$program --help \
          >"$output/valgrind-$program.stdout" \
          2>"$output/valgrind-$program.log"
      printf "%s\n" "$?" >"$output/valgrind-$program.status"
    done
    set -e
    chmod -R a+rwX "$output"
  '
