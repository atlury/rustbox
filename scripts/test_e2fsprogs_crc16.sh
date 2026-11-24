#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
set -eu
root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
case "$#" in
    0) set -- ;;
    1) test "$1" = --all-engines; set -- -e RUSTBOX_CRC16_ALL=1 ;;
    *) echo "usage: $0 [--all-engines]" >&2; exit 2 ;;
esac
exec docker run --rm -i "$@" --network none --platform linux/amd64 \
    -v "$root:/work:ro" -v rustbox-e2fsprogs-1.47.4:/rustbox-e2fsprogs:ro \
    --workdir /tmp rustbox-e2fsprogs:2026-11-24 sh -eu <<'PILOT'
export LC_ALL=C TZ=UTC
src=/work/work/upstream/e2fsprogs-1.47.4/lib
oracle=/rustbox-e2fsprogs/oracle-gcc/lib
canon=/rustbox-e2fsprogs/stage-gcc/sbin
crates=/work/work/analysis/e2fsprogs-1.47.4/program-translations
cd "$src/ext2fs"
sha256sum -c <<'HASHES'
f6b9d7d686c7a9d45d2099eb2c084069e2204537d1828fa6ebfd14cf88fdc46b  crc16.c
6fbf36bd4b8c054a1dd5a5c0ddd5ac1b2438e99e8b0b08ad2a7090a249144954  crc16.h
HASHES
cd /tmp
gcc -O2 -I"$oracle" -I"$src" -Dext2fs_crc16=canonical_ext2fs_crc16 \
    -c "$src/ext2fs/crc16.c" -o canonical.o
rustc --edition=2021 --crate-type=lib --emit=obj -C opt-level=s -C panic=abort \
    /work/compat/e2fsprogs/crc16_abi.rs -o candidate.o
gcc -Wall -Wextra -Werror -O2 -I"$src/ext2fs" \
    /work/tests/e2fsprogs-crc16/differential.c canonical.o candidate.o -o compare
./compare

set --
if [ "${RUSTBOX_CRC16_ALL:-0}" = 1 ]; then set -- --all-engines; fi
python3 /work/scripts/check_e2fsprogs_crc16_engines.py "$crates" /tmp/engines /tmp/candidate.o "$@"
ln -s /tmp/engines/e2fsck /tmp/e2fsck
if [ "${RUSTBOX_CRC16_ALL:-0}" = 1 ]; then
    python3 /work/tests/e2fsprogs-hybrid-differential.py \
        --canonical-root /rustbox-e2fsprogs/stage-gcc --hybrid-root /tmp/engines \
        --output /tmp/all-engines.json
fi

# uninit_bg without metadata_csum selects the legacy descriptor CRC16.
truncate -s 32M fs.img
"$canon/mke2fs" -Fq -t ext4 -O uninit_bg,^metadata_csum -b 1024 fs.img
sha256sum fs.img > image.sha256
"$canon/e2fsck" -fn fs.img > canonical.stdout 2> canonical.stderr
./e2fsck -fn fs.img > candidate.stdout 2> candidate.stderr
cmp canonical.stdout candidate.stdout
cmp canonical.stderr candidate.stderr
# Confirm actual calls into the candidate in a successful read-only check.
valgrind --tool=callgrind --callgrind-out-file=callgrind.out --log-file=valgrind.log \
    ./e2fsck -fn fs.img > /dev/null 2> check.stderr
grep -Eq '^(c?fn)=.*ext2fs_crc16$' callgrind.out
sha256sum -c image.sha256
echo 'e2fsck matched canonical output and status, exercised ext2fs_crc16, and preserved the image'

fixture=/work/work/upstream/e2fsprogs-1.47.4/tests/f_uninit_checksum_bad
export E2FSCK_TIME=1700000000 E2FSPROGS_FAKE_TIME=1700000000
for variant in canonical candidate; do
    mkdir "$variant"
    gzip -dc "$fixture/image.gz" > "$variant/fs.img"
    case "$variant" in
        canonical) binary=$canon/e2fsck ;;
        candidate) binary=/tmp/e2fsck ;;
    esac
    (
        cd "$variant"
        status=0
        "$binary" -fy -N test_filesys fs.img > repair.stdout 2> repair.stderr || status=$?
        test "$status" -eq 1
        "$binary" -fy -N test_filesys fs.img > recheck.stdout 2> recheck.stderr
        { cat repair.stderr repair.stdout; echo 'Exit status is 1'; } > pass1
        { cat recheck.stderr recheck.stdout; echo 'Exit status is 0'; } > pass2
        for pass in 1 2; do
            sed -f "$fixture/../filter.sed" "pass$pass" > filtered
            diff -u "$fixture/expect.$pass" filtered
        done
    )
done
for artifact in repair.stdout repair.stderr recheck.stdout recheck.stderr fs.img; do
    cmp "canonical/$artifact" "candidate/$artifact"
done
echo 'Upstream f_uninit_checksum_bad repair and recheck matched, including image bytes'
PILOT
