#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
"$root/scripts/build_gawk_hybrid.sh"

RUSTBOX_TOOL_IMAGE=rustbox-gawk:2026-11-22 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    output=/work/work/analysis/gawk-5.4.0/hybrid
    hybrid=/work/build/gawk-5.4.0-hybrid
    canonical=/rustbox-gawk/normalized-gcc
    rm -rf "$output"
    mkdir -p "$output"

    python3 /work/tests/gawk-oracle-differential.py \
      --gcc-build "$canonical" --clang-build "$hybrid" \
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
    ln -s "$hybrid/gawk" "$installed"
    set +e
    runuser --user=nobody -- make -C "$canonical" -k -j"$(nproc)" check \
      >"$output/upstream-tests.log" 2>&1
    check_status=$?
    set -e
    restore
    trap - EXIT HUP INT TERM
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
      cp /rustbox-gawk/normalized-source/test/timeout.ok \
        "$output/timeout-expected"
      cp "$canonical/test/_timeout" "$output/timeout-actual"
    else
      test "$differences" -eq 0
    fi
    if grep -E "make(\[[0-9]+\])?: \*\*\*" "$output/upstream-tests.log" \
         | grep -Ev "\[[^]]*: (pma|pma-tests|check-recursive|check)\] Error" \
         | grep -q .; then
      exit 1
    fi

    for implementation in hybrid canonical; do
      case $implementation in
        hybrid) binary=$hybrid/gawk ;;
        canonical) binary=$canonical/gawk ;;
      esac
      valgrind --leak-check=full --show-leak-kinds=all \
        --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
        --log-file="$output/valgrind-$implementation.log" \
        "$binary" --version >"$output/valgrind-$implementation.out" 2>&1
      grep -q "ERROR SUMMARY: 0 errors" "$output/valgrind-$implementation.log"
      grep -q "definitely lost: 0 bytes" "$output/valgrind-$implementation.log"
      grep -q "indirectly lost: 0 bytes" "$output/valgrind-$implementation.log"
      grep -q "possibly lost: 0 bytes" "$output/valgrind-$implementation.log"
    done
    cmp "$output/valgrind-canonical.out" "$output/valgrind-hybrid.out"
  '
