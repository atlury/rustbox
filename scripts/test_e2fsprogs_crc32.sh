#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
set -eu
root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
exec docker run --rm -i --network none --platform linux/amd64 \
    -v "$root:/work:ro" -v rustbox-e2fsprogs-1.47.4:/oracle:ro \
    --workdir /tmp rustbox-e2fsprogs:2026-11-24 sh -eu <<'CHECK'
src=/work/work/upstream/e2fsprogs-1.47.4/lib
lib=/oracle/oracle-gcc/lib
cd "$src/ext2fs"
sha256sum -c <<'HASH'
453108320cc8e0ca668f48cf875224eee1aeefa65aa54d6f1360ed44bc611718  crc32c.c
HASH
cd /tmp
gcc -O2 -I"$lib" -I"$lib/ext2fs" -I"$src" -I"$src/ext2fs" \
    -Dext2fs_crc32c_le=canonical_le -Dext2fs_crc32_be=canonical_be \
    -c "$src/ext2fs/crc32c.c" -o canonical.o
rustc --edition=2021 --crate-type=lib --emit=obj -C opt-level=3 -C panic=abort \
    /work/compat/e2fsprogs/crc32_abi.rs -o candidate.o
gcc -Wall -Wextra -Werror -O2 /work/tests/e2fsprogs-crc32/differential.c \
    canonical.o candidate.o -o compare
./compare
# Feed the canonical test program and its original static vectors to the replacement.
sed -n '/^#ifdef UNITTEST/,$p' "$src/ext2fs/crc32c.c" > vectors.inc
{ echo '#include <stdio.h>'; echo '#include <stdint.h>'; echo '#include <stddef.h>';
  echo 'uint32_t ext2fs_crc32c_le(uint32_t,const uint8_t *,size_t);';
  echo 'uint32_t ext2fs_crc32_be(uint32_t,const uint8_t *,size_t);';
  cat vectors.inc; } > vectors.c
gcc -O2 -DUNITTEST vectors.c candidate.o -o vectors
./vectors
CHECK
