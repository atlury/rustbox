#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
"$root/scripts/build_acl_hybrid.sh"

RUSTBOX_TOOL_IMAGE=rustbox-acl:2026-11-21 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    output=/work/work/analysis/acl-2.4.0/hybrid
    hybrids=/work/build/acl-2.4.0-hybrid
    canonical=/rustbox-acl/normalized-gcc
    test_build=/rustbox-acl/hybrid-test
    ordinary_tests="test/cp.run test/getfacl-lfs.run test/getfacl-noacl.run test/getfacl-recursive.run test/malformed-restore.run test/misc.run test/setfacl-X.run test/root/getfacl.run test/root/restore.run test/root/setfacl.run test/nfs/nfsacl.run test/nfs/nfs-dir.run test/restore.run test/sbits-restore.run test/utf8-filenames.run"
    rm -rf "$output" "$test_build"
    mkdir -p "$output"

    python3 /work/tests/acl-oracle-differential.py \
      --gcc-directory /work/work/analysis/acl-2.4.0/oracle --gcc-suffix gcc \
      --clang-directory "$hybrids" --clang-suffix hybrid \
      --output "$output/differential.json"

    cp -a "$canonical" "$test_build"
    for utility in chacl getfacl setfacl; do
      cp "$hybrids/$utility-hybrid" "$test_build/$utility"
    done
    cd "$test_build"
    if make check TESTS="test/root/permissions.run" \
        >"$output/platform-permissions.log" 2>&1; then
      cat "$output/platform-permissions.log"
      echo "ACL hybrid container permission test unexpectedly passed" >&2
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
    for implementation in canonical hybrid; do
      target=hybrid-valgrind-target
      rm -f "$target"
      printf "payload\n" > "$target"
      case $implementation in
        canonical) directory=$canonical; suffix= ;;
        hybrid) directory=$hybrids; suffix=-hybrid ;;
      esac
      valgrind --leak-check=full --show-leak-kinds=all \
        --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
        --log-file="$output/valgrind-setfacl-$implementation.log" \
        "$directory/setfacl$suffix" -m u:12345:rw- "$target"
      valgrind --leak-check=full --show-leak-kinds=all \
        --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
        --log-file="$output/valgrind-getfacl-$implementation.log" \
        "$directory/getfacl$suffix" -n "$target" \
        >"$output/valgrind-getfacl-$implementation.out"
      for utility in setfacl getfacl; do
        grep -q "ERROR SUMMARY: 0 errors" \
          "$output/valgrind-$utility-$implementation.log"
        sed -n "/HEAP SUMMARY/,+2p" \
          "$output/valgrind-$utility-$implementation.log" \
          | sed "s/^==[0-9]*== *//" \
          >"$output/valgrind-$utility-$implementation-heap"
      done
    done
    cmp "$output/valgrind-getfacl-canonical.out" \
      "$output/valgrind-getfacl-hybrid.out"
    grep -q "total heap usage: 10 allocs, 10 frees, 786 bytes allocated" \
      "$output/valgrind-setfacl-canonical-heap"
    grep -q "total heap usage: 12 allocs, 12 frees, 950 bytes allocated" \
      "$output/valgrind-setfacl-hybrid-heap"
    grep -q "total heap usage: 4 allocs, 4 frees, 4,596 bytes allocated" \
      "$output/valgrind-getfacl-canonical-heap"
    grep -q "total heap usage: 8 allocs, 8 frees, 4,920 bytes allocated" \
      "$output/valgrind-getfacl-hybrid-heap"
  '
