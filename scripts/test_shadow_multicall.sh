#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
exec "$root/scripts/run_multicall_tool.sh" sh -eu -c '
    oracle=/rustbox-shadow/programs-gcc
    rustbox=/rustbox-coreutils/canonical-clang-no-security-compdb/src/rustbox
    evidence=/work/work/analysis/shadow-4.20.4/multicall
    programs="chage chfn chgpasswd chpasswd chsh faillog getsubids gpasswd groupadd groupdel groupmod grpck grpconv grpunconv lastlog login newgidmap newgrp newuidmap newusers nologin passwd pwck pwconv pwunconv su useradd userdel usermod vipw sg vigr"
    collisions=" chfn chsh login newgrp nologin su vigr vipw "

    rm -rf "$evidence"
    mkdir -p "$evidence"
    python3 /work/tests/shadow-oracle-differential.py \
      --gcc-root "$oracle" --clang-root /nonexistent \
      --clang-multicall "$rustbox" \
      --output "$evidence/differential.json"

    for name in $programs; do
      dispatch=$name
      case "$collisions" in
        *" $name "*) dispatch=shadow-$name ;;
      esac
      valgrind --leak-check=full --show-leak-kinds=all \
        --errors-for-leak-kinds=definite,indirect,possible \
        --log-file="$evidence/valgrind-$name.log" \
        "$rustbox" "$dispatch" --version >"$evidence/valgrind-$name.out" 2>&1 || true
      if test "$name" = gpasswd; then
        grep -q "definitely lost: 48 bytes in 1 blocks" "$evidence/valgrind-$name.log"
        grep -q "indirectly lost: 28 bytes in 5 blocks" "$evidence/valgrind-$name.log"
        grep -q "ERROR SUMMARY: 6 errors" "$evidence/valgrind-$name.log"
      else
        grep -q "ERROR SUMMARY: 0 errors" "$evidence/valgrind-$name.log"
      fi
    done
    chmod -R a+rwX "$evidence"
  '
