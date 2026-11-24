#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
set -eu
root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
exec docker run --rm -i --network none --platform linux/amd64 \
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

# Remove the translated definition before compilation so inlined copies cannot
# satisfy the engine's calls. The original finalized translation stays intact.
cp -R "$crates/e2fsck/e2fsck-final" engine
module=$(find engine -path '*/lib/ext2fs/crc16.rs')
printf '%s  %s\n' c3e5eff63f35648b28420174e58a0646ab5ec29d93e9d37321c5f557beed45cd "$module" | sha256sum -c
printf '%s\n' '// ext2fs_crc16 is supplied by the Rustbox CRC16 object.' > "$module"
# Reuse only the locked bitfields dependency from the release translation.
deps=$crates/cargo-target/e2fsck/release/deps
set -- "$deps"/libc2rust_bitfields-*.rlib
test "$#" -eq 1
rustc +nightly-2023-04-15 --edition=2021 --crate-type=staticlib --crate-name e2fsck_audit \
    -C opt-level=3 --cap-lints=allow -L "dependency=$deps" --extern "c2rust_bitfields=$1" \
    engine/lib.rs -o engine.a
clang-18 -O2 -ffunction-sections -fdata-sections -Wl,--gc-sections \
    -DRUSTBOX_E2FSPROGS_ENTRY=rustbox_e2fsprogs_e2fsck_main \
    /work/bridges/e2fsprogs_program_main.c engine.a \
    candidate.o -lblkid -luuid -lfuse3 -ldl -lpthread -lm -o e2fsck

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
