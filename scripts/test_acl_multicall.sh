#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-file:2026-11-20 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    output=/work/work/analysis/acl-2.4.0/multicall
    rustbox=/rustbox-coreutils/canonical-clang-no-security-compdb/src/rustbox
    canonical=/rustbox-acl/normalized-gcc
    test_build=/rustbox-acl/multicall-test
    dispatch=/rustbox-acl/multicall-dispatch
    ordinary_tests="test/cp.run test/getfacl-lfs.run test/getfacl-noacl.run test/getfacl-recursive.run test/malformed-restore.run test/misc.run test/setfacl-X.run test/root/getfacl.run test/root/restore.run test/root/setfacl.run test/nfs/nfsacl.run test/nfs/nfs-dir.run test/restore.run test/sbits-restore.run test/utf8-filenames.run"
    rm -rf "$output" "$test_build" "$dispatch"
    mkdir -p "$output" "$dispatch"

    for utility in chacl getfacl setfacl; do
      ln -s "$rustbox" "$dispatch/$utility-rustbox"
    done
    python3 /work/tests/acl-oracle-differential.py \
      --gcc-directory /work/work/analysis/acl-2.4.0/oracle --gcc-suffix gcc \
      --clang-directory "$dispatch" --clang-suffix rustbox \
      --output "$output/differential.json"

    cp -a "$canonical" "$test_build"
    for utility in chacl getfacl setfacl; do
      cp "$rustbox" "$test_build/$utility"
    done
    cd "$test_build"
    if make check TESTS="test/root/permissions.run" \
        >"$output/platform-permissions.log" 2>&1; then
      cat "$output/platform-permissions.log"
      echo "ACL multicall container permission test unexpectedly passed" >&2
      exit 1
    fi
    grep -q "# TOTAL: 1" "$output/platform-permissions.log"
    grep -q "# FAIL:  1" "$output/platform-permissions.log"
    if make -j"$(nproc)" check TESTS="$ordinary_tests" \
        >"$output/upstream-tests.log" 2>&1; then
      cat "$output/upstream-tests.log"
    else
      status=$?
      cat "$output/upstream-tests.log"
      exit "$status"
    fi

    cd /rustbox-acl
    target=hybrid-valgrind-target
    rm -f "$target"
    printf "payload\n" > "$target"
    valgrind --leak-check=full --show-leak-kinds=all \
      --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
      --log-file="$output/valgrind-setfacl.log" \
      "$rustbox" setfacl -m u:12345:rw- "$target"
    valgrind --leak-check=full --show-leak-kinds=all \
      --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
      --log-file="$output/valgrind-getfacl.log" \
      "$rustbox" getfacl -n "$target" \
      >"$output/valgrind-getfacl.out"
    for utility in setfacl getfacl; do
      grep -q "ERROR SUMMARY: 0 errors" "$output/valgrind-$utility.log"
      grep -q "All heap blocks were freed -- no leaks are possible" \
        "$output/valgrind-$utility.log"
      sed -n "/HEAP SUMMARY/,+2p" "$output/valgrind-$utility.log" \
        | sed "s/^==[0-9]*== *//" >"$output/valgrind-$utility-heap"
      cmp "$output/valgrind-$utility-heap" \
        "/work/work/analysis/acl-2.4.0/hybrid/valgrind-$utility-hybrid-heap"
    done
    cmp "$output/valgrind-getfacl.out" \
      "/work/work/analysis/acl-2.4.0/hybrid/valgrind-getfacl-hybrid.out"
  '
