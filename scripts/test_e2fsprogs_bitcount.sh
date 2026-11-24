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
sha256sum -c <<'HASH'
6be65f6d560afa9849a99dc11c5ca490fe1089002c2416bb6874a3a6b589d8fa  bitops.c
HASH
cd /tmp
gcc -O2 -DOMIT_COM_ERR -I"$lib" -I"$lib/ext2fs" -I"$src" -I"$src/ext2fs" \
    -c "$src/ext2fs/bitops.c" -o canonical.o
rustc --edition=2021 --crate-type=lib --emit=obj -C opt-level=3 -C panic=abort \
    /work/compat/e2fsprogs/bitcount.rs -o candidate.o
gcc -Wall -Wextra -Werror -O2 /work/tests/e2fsprogs-bitcount/differential.c \
    canonical.o candidate.o -o compare
./compare
# Use the same two compiled engine archives selected by the default release.
# Redirect cross-object calls in these disposable standalone binaries.
engines=/work/work/analysis/e2fsprogs-1.47.4/program-translations/rustbox-checksums
canon=/oracle/stage-gcc/sbin
objcopy --redefine-sym rustbox_e2fsprogs_bitcount=__wrap_ext2fs_bitcount candidate.o wrapped.o
for name in e2fsck resize2fs; do
    clang-18 -O2 -Wl,--gc-sections -Wl,--wrap=ext2fs_bitcount \
        "-DRUSTBOX_E2FSPROGS_ENTRY=rustbox_e2fsprogs_${name}_main" \
        /work/bridges/e2fsprogs_program_main.c "$engines/$name/lib${name}_audit.a" \
        "$engines/crc16.o" "$engines/crc32.o" wrapped.o \
        -lblkid -luuid -lfuse3 -ldl -lpthread -lm -o "/tmp/$name"
done
export E2FSCK_TIME=1700000000 E2FSPROGS_FAKE_TIME=1700000000
mkdir reference candidate
truncate -s 32M reference/fs.img
"$canon/mke2fs" -Fq -t ext4 -b 1024 -E lazy_itable_init=0,lazy_journal_init=0 reference/fs.img
cp reference/fs.img candidate/fs.img
for variant in reference candidate; do
    (
        cd "$variant"
        check() {
            name=$1
            shift
            if [ "$variant" = reference ]; then
                "$canon/$name" "$@"
            else
                valgrind --tool=callgrind --callgrind-out-file="$name.calls" \
                    --log-file="$name.log" "/tmp/$name" "$@"
            fi
        }
        check e2fsck -fn fs.img > check.out 2> check.err
        sha256sum fs.img > before-grow.sha256
        truncate -s 40M fs.img
        check resize2fs fs.img > grow.out 2> grow.err
        "$canon/e2fsck" -fn fs.img > recheck.out 2> recheck.err
    )
done
for file in check.out check.err before-grow.sha256 grow.out grow.err fs.img recheck.out recheck.err; do
    cmp "reference/$file" "candidate/$file"
done
for name in e2fsck resize2fs; do
    grep -Eq '^(c?fn)=.*__wrap_ext2fs_bitcount$' "candidate/$name.calls"
    echo "$name exercised the replacement and matched the canonical filesystem run"
done
CHECK
