#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
groups=${1-}
RUSTBOX_TOOL_IMAGE=rustbox-bison:2026-11-23 \
  exec "$root/scripts/run_tool.sh" env RUSTBOX_BISON_TEST_GROUPS="$groups" sh -eu -c '
    build=/rustbox-bison/oracle-v3-gcc
    canonical=$build/src/.rustbox-canonical-bison
    binary=$build/src/bison
    rustbox=/rustbox-coreutils/canonical-clang-no-security-compdb/src/rustbox
    testsuite=/rustbox-bison/source-pristine/tests/testsuite
    output=/work/work/analysis/bison-3.8.2/multicall
    groups=${RUSTBOX_BISON_TEST_GROUPS-}

    restore()
    {
      rm -f "$binary"
      if test -f "$canonical"; then
        mv "$canonical" "$binary"
      fi
    }
    if test -f "$canonical"; then
      restore
    fi
    mv "$binary" "$canonical"
    ln -s "$rustbox" "$binary"
    trap restore EXIT HUP INT TERM
    mkdir -p "$output"
    cd "$build"
    if test -n "$groups"; then
      "$testsuite" -C tests -j"$(nproc)" $groups \
        >"$output/upstream-tests-targeted.log" 2>&1
      grep -Eq "1 test was successful|All 1 test was successful" \
        "$output/upstream-tests-targeted.log"
    else
      set +e
      "$testsuite" -C tests -j"$(nproc)" \
        >"$output/upstream-tests.log" 2>&1
      status=$?
      set -e
      test "$status" -eq 1
      expected="47 53 58 63 213 465 466 467 468 571 572 573 574 575 576 577 578 579 580 581 582 583 584 585 586 587 588 589 590 591 592 593 594 595 596 597 598 599 600 601 602 603 651 692 693 694 695 696 697 698 699 700 701 702 703 704"
      actual=$(sed -n '\''s/^[[:space:]]*\([0-9][0-9]*\): .*FAILED.*/\1/p'\'' \
        "$output/upstream-tests.log" | sort -n | tr '\''\n'\'' '\'' '\'' | sed '\''s/ $//'\'')
      test "$actual" = "$expected"
      grep -q "ERROR: 763 tests were run" "$output/upstream-tests.log"
      grep -q "56 failed unexpectedly" "$output/upstream-tests.log"
      grep -q "13 tests were skipped" "$output/upstream-tests.log"
    fi
  '
