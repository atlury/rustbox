#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
exec "$root/scripts/run_multicall_tool.sh" sh -eu -c '
    output=/work/work/analysis/gzip-1.14/multicall
    rustbox=/rustbox-coreutils/canonical-clang-no-security-compdb/src/rustbox
    canonical=/rustbox-gzip/normalized-install-gcc/usr/bin
    dispatch=/rustbox-gzip/multicall-dispatch
    rm -rf "$output" "$dispatch"
    mkdir -p "$output" "$dispatch"
    for utility in gzip gunzip zcat uncompress zcmp zdiff zforce zgrep zegrep zfgrep zless zmore znew gzexe; do
      ln -s "$rustbox" "$dispatch/$utility"
    done
    ln -s "$rustbox" "$dispatch/less"

    python3 /work/tests/gzip-oracle-differential.py \
      --gcc-directory "$canonical" --clang-directory "$dispatch" \
      --applets gzip gunzip zcat uncompress zcmp zdiff zforce zgrep zegrep zfgrep zless zmore znew gzexe \
      --canonical-less /work/work/analysis/less-710/normalized/gcc/less \
      --output "$output/differential.json"

    printf "alpha beta gamma\n%.0s" $(seq 1 2048) >"$output/input"
    printf "alpha delta gamma\n%.0s" $(seq 1 2048) >"$output/other"
    "$canonical/gzip" -n -9 -c "$output/input" >"$output/canonical.gz"
    "$canonical/gzip" -n -9 -c "$output/other" >"$output/other.gz"
    valgrind --leak-check=full --show-leak-kinds=all \
      --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
      --log-file="$output/valgrind-compress.log" \
      "$rustbox" gzip -n -9 -c "$output/input" >"$output/multicall.gz"
    valgrind --leak-check=full --show-leak-kinds=all \
      --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
      --log-file="$output/valgrind-decompress.log" \
      "$rustbox" gzip -dc "$output/canonical.gz" >"$output/multicall.out"
    for operation in compress decompress; do
      grep -q "ERROR SUMMARY: 0 errors" "$output/valgrind-$operation.log"
      grep -q "All heap blocks were freed -- no leaks are possible" \
        "$output/valgrind-$operation.log"
    done
    set +e
    valgrind --leak-check=full --show-leak-kinds=all \
      --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
      --log-file="$output/valgrind-zcmp.log" \
      "$rustbox" zcmp "$output/canonical.gz" "$output/other.gz" >/dev/null
    zcmp_status=$?
    valgrind --leak-check=full --show-leak-kinds=all \
      --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
      --log-file="$output/valgrind-zdiff.log" \
      "$rustbox" zdiff "$output/canonical.gz" "$output/other.gz" >/dev/null
    zdiff_status=$?
    valgrind --leak-check=full --show-leak-kinds=all \
      --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
      --log-file="$output/valgrind-zgrep.log" \
      "$rustbox" zgrep delta "$output/other.gz" >/dev/null
    zgrep_status=$?
    LESS=-FX valgrind --leak-check=full --show-leak-kinds=all \
      --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
      --log-file="$output/valgrind-zless.log" \
      "$rustbox" zless "$output/other.gz" >/dev/null
    zless_status=$?
    valgrind --leak-check=full --show-leak-kinds=all \
      --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
      --log-file="$output/valgrind-zmore.log" \
      "$rustbox" zmore "$output/other.gz" >/dev/null
    zmore_status=$?
    cp "$output/canonical.gz" "$output/legacy.Z"
    valgrind --leak-check=full --show-leak-kinds=all \
      --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
      --log-file="$output/valgrind-znew.log" \
      "$rustbox" znew -Pt "$output/legacy" >/dev/null
    znew_status=$?
    set -e
    test "$zcmp_status" -eq 1
    test "$zdiff_status" -eq 1
    test "$zgrep_status" -eq 99
    test "$zless_status" -eq 0
    test "$zmore_status" -eq 0
    test "$znew_status" -eq 0
    for operation in zcmp zdiff; do
      grep -q "ERROR SUMMARY: 0 errors" "$output/valgrind-$operation.log"
      grep -q "definitely lost: 0 bytes in 0 blocks" "$output/valgrind-$operation.log"
      grep -q "indirectly lost: 0 bytes in 0 blocks" "$output/valgrind-$operation.log"
      grep -q "possibly lost: 0 bytes in 0 blocks" "$output/valgrind-$operation.log"
    done
    grep -q "ERROR SUMMARY: 1 errors" "$output/valgrind-zgrep.log"
    grep -q "definitely lost: 0 bytes in 0 blocks" "$output/valgrind-zgrep.log"
    grep -q "indirectly lost: 0 bytes in 0 blocks" "$output/valgrind-zgrep.log"
    grep -q "possibly lost: 128 bytes in 1 blocks" "$output/valgrind-zgrep.log"
    grep -q "still reachable: 112,870 bytes in 19 blocks" "$output/valgrind-zgrep.log"
    grep -q "ERROR SUMMARY: 0 errors" "$output/valgrind-zless.log"
    grep -q "All heap blocks were freed -- no leaks are possible" \
      "$output/valgrind-zless.log"
    grep -q "ERROR SUMMARY: 0 errors" "$output/valgrind-zmore.log"
    grep -q "All heap blocks were freed -- no leaks are possible" \
      "$output/valgrind-zmore.log"
    grep -q "ERROR SUMMARY: 0 errors" "$output/valgrind-znew.log"
    grep -q "All heap blocks were freed -- no leaks are possible" \
      "$output/valgrind-znew.log"
    mkdir "$output/gzexe-runtime"
    printf "#!/bin/sh\nprintf \"gzexe payload\\n\"\n" \
      > "$output/gzexe-runtime/tool"
    chmod 755 "$output/gzexe-runtime/tool"
    cp "$output/gzexe-runtime/tool" "$output/gzexe-runtime/original"
    valgrind --leak-check=full --show-leak-kinds=all \
      --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
      --log-file="$output/valgrind-gzexe.log" \
      "$rustbox" gzexe "$output/gzexe-runtime/tool" >/dev/null
    grep -q "ERROR SUMMARY: 0 errors" "$output/valgrind-gzexe.log"
    grep -q "All heap blocks were freed -- no leaks are possible" \
      "$output/valgrind-gzexe.log"
    PATH="$dispatch:/usr/bin:/bin" "$output/gzexe-runtime/tool" \
      > "$output/gzexe-runtime.out"
    grep -qx "gzexe payload" "$output/gzexe-runtime.out"
    "$rustbox" gzexe -d "$output/gzexe-runtime/tool" >/dev/null
    cmp "$output/gzexe-runtime/original" "$output/gzexe-runtime/tool"
    cmp "$output/canonical.gz" "$output/multicall.gz"
    cmp "$output/input" "$output/multicall.out"
  '
