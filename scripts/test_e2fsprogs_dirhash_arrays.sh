#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
set -eu
root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
exec docker run --rm -i --network none --platform linux/amd64 \
    -v "$root:/work:ro" -v rustbox-e2fsprogs-1.47.4:/oracle:ro \
    --workdir /tmp rustbox-e2fsprogs:2026-11-24 sh -eu <<'CHECK'
export LC_ALL=C TZ=UTC
src=/work/work/upstream/e2fsprogs-1.47.4/lib
lib=/oracle/oracle-gcc/lib
cd "$src/ext2fs"
sha256sum -c <<'PIN'
2788ae0148645b88c2431ba3de263cf8fce5395cae55d0ba0032b3d42a3c0b81  dirhash.c
PIN
cd /tmp
engines=work/analysis/e2fsprogs-1.47.4/program-translations/rustbox-e2fsprogs-shared
archive=$engines/debugfs/libdebugfs_audit.a
mkdir /tmp/pilot
python3 -B /work/scripts/check_e2fsprogs_dirhash_arrays.py /work/work/analysis/rustbox-multicall-link.json "$archive" /tmp/pilot
gcc -O2 -ffunction-sections -I"$lib" -I"$lib/ext2fs" -I"$src" -I"$src/ext2fs" \
    -Dext2fs_dirhash=reference_dirhash -Dext2fs_dirhash2=reference_dirhash2 \
    -c "$src/ext2fs/dirhash.c" -o canonical.o
set -- /tmp/pilot/libdebugfs_audit.a "/work/$engines/crc16.o" "/work/$engines/crc32.o" \
    "/work/$engines/bitcount.o" -lblkid -luuid -lfuse3 -ldl -lpthread -lm
gcc -Wall -Wextra -Werror -O2 -Wl,--gc-sections /work/tests/e2fsprogs-dirhash/differential.c \
    canonical.o "$@" -o compare
./compare
clang-18 -O2 -Wl,--gc-sections -DRUSTBOX_E2FSPROGS_ENTRY=rustbox_e2fsprogs_debugfs_main \
    /work/bridges/e2fsprogs_program_main.c "$@" -o debugfs
mkdir reference candidate
for version in 1 2 4 5; do
    for name in example abcdefghijklmnop 0123456789abcdef0123456789abcdef01234567; do
        command="dx_hash -h $version -s 01234567-89ab-cdef-fedc-ba9876543210 $name"
        /oracle/stage-gcc/sbin/debugfs -R "$command" > reference/out 2> reference/err
        ./debugfs -R "$command" > candidate/out 2> candidate/err
        grep -q 'Hash of ' reference/out
        cmp reference/out candidate/out
        cmp reference/err candidate/err
    done
done
valgrind --error-exitcode=99 --quiet ./compare --memcheck
echo '12 canonical debugfs commands matched stdout and stderr'
CHECK
