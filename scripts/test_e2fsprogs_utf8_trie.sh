#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
set -eu
root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
if [ "$#" -ne 1 ]; then echo "usage: $0 PILOT_RESULTS_DIRECTORY" >&2; exit 2; fi
docker run --rm -i --network none --platform linux/amd64 -v "$root:/work:ro" \
    -v rustbox-e2fsprogs-1.47.4:/oracle:ro --workdir /tmp rustbox-e2fsprogs:2026-11-24 sh -seu -- "$1" <<'CHECK'
export LC_ALL=C TZ=UTC
pilot=/work/$1
src=/work/work/upstream/e2fsprogs-1.47.4/lib
lib=/oracle/oracle-gcc/lib
shared=/work/work/analysis/e2fsprogs-1.47.4/program-translations/rustbox-e2fsprogs-shared
archive=$pilot/libdebugfs_audit.a
expected=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["candidate_sha256"])' "$pilot/result.json")
echo "$expected  $archive" | sha256sum -c
echo "041aa8fcf429be699e79e25086bd32c42b0e80ee3a3bf7392fee1dfdca274936  $src/ext2fs/nls_utf8.c" | sha256sum -c
rustc +nightly-2023-04-15 --edition=2021 --crate-type=lib --emit=metadata -A warnings -F unsafe-code /work/compat/e2fsprogs/utf8_trie.rs
{ echo '#![no_std]'; cat /work/compat/e2fsprogs/utf8_trie.rs /work/tests/e2fsprogs-utf8-trie/ffi.rs; } > lookup.rs
rustc +nightly-2023-04-15 --edition=2021 --crate-type=lib --emit=obj -C opt-level=2 -C panic=abort lookup.rs
set -- "$archive" "$shared/crc16.o" "$shared/crc32.o" "$shared/bitcount.o" -lblkid -luuid -lfuse3 -ldl -lpthread -lm
gcc -O2 -Wall -Wextra -Werror -Wno-unused-parameter -I"$lib" -I"$lib/ext2fs" -I"$src" -I"$src/ext2fs" \
    -Wl,--gc-sections /work/tests/e2fsprogs-utf8-trie/differential.c lookup.o "$@" -o compare
./compare
valgrind --error-exitcode=99 --log-file=memcheck.log ./compare --memcheck
grep 'ERROR SUMMARY: 0 errors' memcheck.log
clang-18 -O2 -Wl,--gc-sections -DRUSTBOX_E2FSPROGS_ENTRY=rustbox_e2fsprogs_debugfs_main \
    /work/bridges/e2fsprogs_program_main.c "$@" -o debugfs
python3 -B /work/tests/e2fsprogs-hangul/debugfs.py /oracle/stage-gcc/sbin/debugfs /tmp/debugfs
CHECK
