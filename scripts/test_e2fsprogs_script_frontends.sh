#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
exec docker run --rm --platform linux/amd64 \
  --volume "$root:/work" \
  --volume rustbox-e2fsprogs-1.47.4:/rustbox-e2fsprogs \
  --workdir /work rustbox-e2fsprogs:2026-11-24 sh -eu -c '
    output=/work/work/analysis/e2fsprogs-1.47.4/script-frontends
    source=/work/work/upstream/e2fsprogs-1.47.4
    for compiler in gcc clang-18; do
      python3 -B /work/tests/e2fsprogs-script-frontends.py \
        --canonical-root "/rustbox-e2fsprogs/stage-$compiler" \
        --native "$output/gcc" --native "$output/clang-18" \
        --source "$source" --output "$output/differential-$compiler.json"
    done

    # Exercise the translated LVM orchestration without touching a real block
    # device.  Both the canonical scripts and native frontends see the same
    # deterministic command oracles; -n keeps every mutating command dry.
    mock=/usr/local/sbin/rustbox-e2fs-mock
    printf "%s\n" \
      "#!/bin/sh" \
      "name=\${0##*/}" \
      "case \"\$name\" in" \
      "  lsblk)" \
      "    case \"\$*\" in" \
      "      *NAME,FSTYPE,MOUNTPOINT*) echo '\''NAME=\"/dev/rustbox-vg/rustbox-lv\" FSTYPE=\"ext4\" MOUNTPOINT=\"/mnt/rustbox-e2scrub-test\"'\'' ;;" \
      "      *NAME,MOUNTPOINT,FSTYPE,TYPE*) echo '\''NAME=\"/dev/rustbox-vg/rustbox-lv\" MOUNTPOINT=\"/mnt/rustbox-e2scrub-test\" FSTYPE=\"ext4\" TYPE=\"lvm\"'\'' ;;" \
      "    esac ;;" \
      "  dumpe2fs) echo '\''Filesystem features: has_journal extent'\'' ;;" \
      "  lvs)" \
      "    case \"\$*\" in" \
      "      *--nameprefixes*) echo \"LVM2_LV_NAME='\''rustbox-lv'\'' LVM2_VG_NAME='\''rustbox-vg'\'' LVM2_LV_ROLE='\''public'\''\" ;;" \
      "      *lv_role=snapshot*) echo '\''/dev/rustbox-vg/rustbox-lv.e2scrub'\'' ;;" \
      "      *lv_snapshot_invalid*) : ;;" \
      "      *) echo '\''/dev/rustbox-vg/rustbox-lv'\'' ;;" \
      "    esac ;;" \
      "  *) exit 0 ;;" \
      "esac" >"$mock"
    chmod 755 "$mock"
    for name in lsblk lvs lvcreate lvremove udevadm dumpe2fs; do
      ln -sf rustbox-e2fs-mock "/usr/local/sbin/$name"
    done
    mkdir -p /mnt/rustbox-e2scrub-test /dev/rustbox-vg
    : >/dev/rustbox-vg/rustbox-lv
    for compiler in gcc clang-18; do
      python3 -B /work/tests/e2fsprogs-script-frontends.py --lvm-only \
        --canonical-root "/rustbox-e2fsprogs/stage-$compiler" \
        --native "$output/gcc" --native "$output/clang-18" \
        --source "$source" --output "$output/lvm-differential-$compiler.json"
    done

    nm -g --defined-only "$output/e2fsprogs-script-frontends.o" \
      >"$output/multicall.symbols"
    test "$(awk '\''$NF ~ /^rustbox_e2fsprogs_(compile_et|mk_cmds|e2scrub|e2scrub_all)_main$/ { n++ } END { print n+0 }'\'' \
      "$output/multicall.symbols")" -eq 4
    test "$(grep -c " rustbox_e2fsprogs_.*_main$" "$output/multicall.symbols")" -eq 4

    readelf -d "$output/gcc/e2fsprogs-script-frontends" >"$output/dynamic.txt"
    test "$(grep -c "Shared library:" "$output/dynamic.txt")" -eq 1
    grep -q "Shared library: \[libc.so.6\]" "$output/dynamic.txt"

    cppcheck --enable=warning,performance,portability --error-exitcode=2 \
      --quiet /work/bridges/e2fsprogs_script_frontends.c 2>"$output/cppcheck.log"
    gcc -std=c11 -Wall -Wextra -fanalyzer -fsyntax-only \
      /work/bridges/e2fsprogs_script_frontends.c 2>"$output/gcc-analyzer.log"
    clang-18 --analyze -std=c11 -Wall -Wextra \
      -Xanalyzer -analyzer-output=text \
      /work/bridges/e2fsprogs_script_frontends.c 2>"$output/clang-analyzer.log"
    test ! -s "$output/cppcheck.log"
    test ! -s "$output/gcc-analyzer.log"
    test ! -s "$output/clang-analyzer.log"

    valgrind --leak-check=full --show-leak-kinds=all --error-exitcode=99 \
      "$output/gcc/e2scrub" -V >"$output/valgrind-e2scrub.out" \
      2>"$output/valgrind-e2scrub.log"
    valgrind --leak-check=full --show-leak-kinds=all --error-exitcode=99 \
      "$output/gcc/e2scrub_all" -V >"$output/valgrind-e2scrub_all.out" \
      2>"$output/valgrind-e2scrub_all.log"
    temporary=$(mktemp -d)
    trap '\''rm -rf "$temporary"'\'' EXIT HUP INT TERM
    cp "$source/lib/et/test_cases/simple.et" "$temporary/simple.et"
    cp "$source/lib/ss/test_cmd.ct" "$temporary/test_cmd.ct"
    cd "$temporary"
    valgrind --leak-check=full --show-leak-kinds=all --error-exitcode=99 \
      "$output/gcc/compile_et" simple.et >"$output/valgrind-compile_et.out" \
      2>"$output/valgrind-compile_et.log"
    valgrind --leak-check=full --show-leak-kinds=all --error-exitcode=99 \
      "$output/gcc/mk_cmds" test_cmd.ct >"$output/valgrind-mk_cmds.out" \
      2>"$output/valgrind-mk_cmds.log"
    for name in e2scrub e2scrub_all compile_et mk_cmds; do
      grep -q "ERROR SUMMARY: 0 errors" "$output/valgrind-$name.log"
      grep -q "All heap blocks were freed" "$output/valgrind-$name.log"
    done
    python3 -B /work/scripts/summarize_e2fsprogs_script_frontends.py \
      --directory "$output" --output "$output/summary.json"
    chmod -R a+rwX "$output"
  '
