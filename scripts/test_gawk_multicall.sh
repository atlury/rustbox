#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-gawk:2026-11-22 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    stage=/rustbox-gawk/multicall
    output=/work/work/analysis/gawk-5.4.0/multicall
    binary=/rustbox-coreutils/canonical-clang-no-security-compdb/src/rustbox
    canonical=/rustbox-gawk/normalized-gcc
    extensions=/work/build/gawk-5.4.0-hybrid/extension/.libs
    rm -rf "$stage" "$output"
    mkdir -p "$stage/extension" "$output"
    ln -s "$binary" "$stage/gawk"
    ln -s "$binary" "$stage/awk"
    ln -s "$extensions" "$stage/extension/.libs"

    python3 /work/tests/gawk-oracle-differential.py \
      --gcc-build "$canonical" --clang-build "$stage" \
      --output "$output/differential.json"

    installed=$canonical/gawk
    saved=$canonical/gawk.rustbox-canonical
    restore()
    {
      if test -e "$saved"; then
        rm -f "$installed"
        mv "$saved" "$installed"
      fi
    }
    trap restore EXIT HUP INT TERM
    test ! -e "$saved"
    mv "$installed" "$saved"
    ln -s "$stage/gawk" "$installed"
    set +e
    runuser --user=nobody -- make -C "$canonical" -k -j"$(nproc)" check \
      >"$output/upstream-tests.log" 2>&1
    check_status=$?
    set -e
    restore
    trap - EXIT HUP INT TERM

    # The canonical PMA second-map test also faults under this x86_64 QEMU
    # environment.  It remains the sole accepted platform-specific failure.
    test "$check_status" -ne 0
    test "$(grep -c "Segmentation fault.*GAWK_PERSIST_FILE=test.pma" \
      "$output/upstream-tests.log")" -eq 1
    test "$(grep -c "Error 139" "$output/upstream-tests.log")" -eq 1
    differences=$(grep -c " differ:" "$output/upstream-tests.log" || true)
    test "$differences" -le 1
    timeout_ignored=$(grep -c "timeout] Error 1 (ignored)" \
      "$output/upstream-tests.log" || true)
    test "$timeout_ignored" -le 1
    if test "$timeout_ignored" -eq 1; then
      if test "$differences" -eq 1; then
        grep -q "/timeout.ok _timeout differ:" "$output/upstream-tests.log"
      fi
      sed "/^2 timed out; trying again$/d" \
        /rustbox-gawk/normalized-source/test/timeout.ok \
        | cmp - "$canonical/test/_timeout"
    else
      test "$differences" -eq 0
    fi
    if grep -E "make(\[[0-9]+\])?: \*\*\*" "$output/upstream-tests.log" \
         | grep -Ev "\[[^]]*: (pma|pma-tests|check-recursive|check)\] Error" \
         | grep -q .; then
      exit 1
    fi

    for name in gawk awk; do
      valgrind --leak-check=full --show-leak-kinds=all \
        --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
        --log-file="$output/valgrind-$name.log" \
        "$stage/$name" --version >"$output/valgrind-$name.out" 2>&1
      grep -q "ERROR SUMMARY: 0 errors" "$output/valgrind-$name.log"
      grep -q "definitely lost: 0 bytes" "$output/valgrind-$name.log"
      grep -q "indirectly lost: 0 bytes" "$output/valgrind-$name.log"
      grep -q "possibly lost: 0 bytes" "$output/valgrind-$name.log"
    done
    cmp "$output/valgrind-gawk.out" "$output/valgrind-awk.out"
  '
