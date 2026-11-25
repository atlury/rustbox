#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
set -eu
root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
if [ "$#" -ne 1 ]; then echo "usage: $0 --multicall | PILOT_RESULTS_DIRECTORY" >&2; exit 2; fi
docker run --rm -i --network none --platform linux/amd64 -v "$root:/work:ro" \
    -v rustbox-e2fsprogs-1.47.4:/oracle:ro -v rustbox-coreutils-9.12:/release:ro --workdir /tmp rustbox-e2fsprogs:2026-11-24 sh -seu -- "$1" <<'CHECK'
export LC_ALL=C TZ=UTC
mode=$1
binary=/release/canonical-clang-no-security-compdb/src/rustbox
src=/work/work/upstream/e2fsprogs-1.47.4/lib
lib=/oracle/oracle-gcc/lib
shared=/work/work/analysis/e2fsprogs-1.47.4/program-translations/rustbox-e2fsprogs-shared
if [ "$mode" = --multicall ]; then
    archive=$(PYTHONPATH=/work/scripts python3 -B - "$binary" <<'SELECT'
import json, sys
from pathlib import Path
from check_cargo_private_inlines import digest
from e2fsprogs_dirhash_archives import candidate_path, control_view
release = json.loads(Path("/work/work/analysis/rustbox-multicall-link.json").read_bytes())
control_view(release)
name, = (k for k in release["e2fsprogs_dirhash_arrays"] if Path(k).parent.name == "debugfs")
row = release["e2fsprogs_dirhash_arrays"][name]
path = Path("/work") / candidate_path(Path(name), row["candidate_sha256"])
if "trie" not in row or digest(path) != row["candidate_sha256"] or digest(Path(sys.argv[1])) != release["binary"]["sha256"]:
    raise ValueError("trie tests require the selected debugfs archive and exact installed ELF")
print(path)
SELECT
)
else
    pilot=/work/$mode
    archive=$pilot/libdebugfs_audit.a
    expected=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["candidate_sha256"])' "$pilot/result.json")
    echo "$expected  $archive" | sha256sum -c
fi
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
if [ "$mode" = --multicall ]; then
    ln -s "$binary" debugfs
else
    clang-18 -O2 -Wl,--gc-sections -DRUSTBOX_E2FSPROGS_ENTRY=rustbox_e2fsprogs_debugfs_main \
        /work/bridges/e2fsprogs_program_main.c "$@" -o debugfs
fi
python3 -B /work/tests/e2fsprogs-hangul/debugfs.py /oracle/stage-gcc/sbin/debugfs /tmp/debugfs
CHECK
