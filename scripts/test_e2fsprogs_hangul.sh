#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
set -eu
root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
if [ "$#" -ne 1 ]; then echo "usage: $0 --multicall | REPOSITORY_RELATIVE_MANIFEST" >&2; exit 2; fi
docker run --rm -i --network none --platform linux/amd64 \
    -v "$root:/work:ro" -v rustbox-e2fsprogs-1.47.4:/oracle:ro -v rustbox-coreutils-9.12:/release:ro \
    --workdir /tmp rustbox-e2fsprogs:2026-11-24 sh -seu -- "$1" <<'CHECK'
export LC_ALL=C TZ=UTC
src=/work/work/upstream/e2fsprogs-1.47.4/lib
lib=/oracle/oracle-gcc/lib
echo "041aa8fcf429be699e79e25086bd32c42b0e80ee3a3bf7392fee1dfdca274936  $src/ext2fs/nls_utf8.c" | sha256sum -c
binary=/release/canonical-clang-no-security-compdb/src/rustbox
archive=$(PYTHONPATH=/work/scripts python3 -B - "$1" "$binary" <<'SELECT'
import json, sys
from pathlib import Path
from check_cargo_private_inlines import digest
from e2fsprogs_dirhash_archives import candidate_path, control_view
if sys.argv[1] == "--multicall":
    link = json.loads(Path("/work/work/analysis/rustbox-multicall-link.json").read_bytes())
    control_view(link)
    if digest(Path(sys.argv[2])) != link["binary"]["sha256"]:
        raise ValueError("test executable differs from the current multicall")
    records = link["e2fsprogs_dirhash_arrays"]
else:
    records = json.loads((Path("/work") / sys.argv[1]).read_bytes())
key, = (k for k in records if Path(k).parent.name == "debugfs")
record = records[key]
path = Path("/work") / candidate_path(Path(key), record["candidate_sha256"])
if "hangul" not in record or digest(path) != record["candidate_sha256"]:
    raise ValueError("expected the checked Hangul archive")
print(path)
SELECT
)
rustc +nightly-2023-04-15 --edition=2021 --crate-type=lib --emit=metadata -A warnings -F unsafe-code /work/compat/e2fsprogs/hangul.rs
gcc -O2 -ffunction-sections -I"$lib" -I"$lib/ext2fs" -I"$src" -I"$src/ext2fs" \
    -Dext2fs_load_nls_table=canonical_load -Dext2fs_check_encoded_name=canonical_validate \
    -Dext2fs_casefold_cmp=canonical_compare -c "$src/ext2fs/nls_utf8.c" -o canonical.o
python3 -B /work/tests/e2fsprogs-hangul/adapter.py
rustc +nightly-2023-04-15 --edition=2021 --crate-type=lib --emit=obj -C opt-level=2 -C panic=abort adapter.rs
gcc -O2 -I"$lib" -I"$lib/ext2fs" -I"$src" -I"$src/ext2fs" -include "$src/ext2fs/nls_utf8.c" \
    /work/tests/e2fsprogs-hangul/leaf.c adapter.o -o leaf
./leaf
mode=$1
shared=/work/work/analysis/e2fsprogs-1.47.4/program-translations/rustbox-e2fsprogs-shared
set -- "$archive" "$shared/crc16.o" "$shared/crc32.o" "$shared/bitcount.o" -lblkid -luuid -lfuse3 -ldl -lpthread -lm
gcc -O2 -Wall -Wextra -Werror -I"$lib" -I"$lib/ext2fs" -I"$src" -I"$src/ext2fs" \
    -Wl,--gc-sections /work/tests/e2fsprogs-hangul/differential.c canonical.o "$@" -o compare
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
