#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
set -eu
root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
case "$#:$*" in
    0:|1:--multicall) ;;
    *) echo "usage: $0 [--multicall]" >&2; exit 2 ;;
esac
reports=$root/work/analysis/e2fsprogs-1.47.4
scratch=$(mktemp -d "$reports/dirhash-test.XXXXXXXX")
trap 'rm -rf "$scratch"' EXIT
docker run --rm -i --network none --platform linux/amd64 \
    -v "$scratch:/results" -v "$root:/work:ro" -v rustbox-e2fsprogs-1.47.4:/oracle:ro \
    -v rustbox-coreutils-9.12:/rustbox-coreutils:ro \
    --workdir /tmp rustbox-e2fsprogs:2026-11-24 sh -seu -- "$@" <<'CHECK'
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
python3 -B /work/tests/e2fsprogs-dirhash/safe-functions.py "/work/$(dirname "$engines")"
release_mode=${1:-}
if [ "$release_mode" = --multicall ]; then
    binary=/rustbox-coreutils/canonical-clang-no-security-compdb/src/rustbox
    object=$(PYTHONPATH=/work/scripts python3 -B - "$binary" "$archive" <<'VERIFY'
import json, sys
from pathlib import Path
from check_cargo_private_inlines import digest
from e2fsprogs_dirhash_archives import candidate_path, control_view
link = json.loads(Path("/work/work/analysis/rustbox-multicall-link.json").read_bytes())
control_view(link)
base = Path(sys.argv[2])
record = link["e2fsprogs_dirhash_arrays"][str(base)]
path = candidate_path(base, record["candidate_sha256"])
if digest(Path(sys.argv[1])) != link["binary"]["sha256"] or digest(Path("/work") / path) != link["source_library_sha256"][str(path)]:
    raise ValueError("directory hash archive or multicall differs from the release")
print(Path("/work") / path)
VERIFY
)
    ln -s "$binary" debugfs
    ln -s "$binary" e2fsck
else
    mkdir /tmp/pilot
    python3 -B /work/scripts/check_e2fsprogs_dirhash_arrays.py /work/work/analysis/rustbox-multicall-link.json "$archive" /tmp/pilot
    object=/tmp/pilot/libdebugfs_audit.a
fi
gcc -O2 -ffunction-sections -I"$lib" -I"$lib/ext2fs" -I"$src" -I"$src/ext2fs" \
    -Dext2fs_dirhash=reference_dirhash -Dext2fs_dirhash2=reference_dirhash2 \
    -c "$src/ext2fs/dirhash.c" -o canonical.o
set -- "$object" "/work/$engines/crc16.o" "/work/$engines/crc32.o" \
    "/work/$engines/bitcount.o" -lblkid -luuid -lfuse3 -ldl -lpthread -lm
gcc -Wall -Wextra -Werror -O2 -Wl,--gc-sections /work/tests/e2fsprogs-dirhash/differential.c \
    canonical.o "$@" -o compare
./compare > compare.log
cat compare.log
if [ "$release_mode" != --multicall ]; then
    clang-18 -O2 -Wl,--gc-sections -DRUSTBOX_E2FSPROGS_ENTRY=rustbox_e2fsprogs_debugfs_main \
        /work/bridges/e2fsprogs_program_main.c "$@" -o debugfs
fi
mkdir reference candidate
commands=0
for version in 1 2 4 5; do
    for name in example abcdefghijklmnop 0123456789abcdef0123456789abcdef01234567; do
        command="dx_hash -h $version -s 01234567-89ab-cdef-fedc-ba9876543210 $name"
        /oracle/stage-gcc/sbin/debugfs -R "$command" > reference/out 2> reference/err
        ./debugfs -R "$command" > candidate/out 2> candidate/err
        grep -q 'Hash of ' reference/out
        cmp reference/out candidate/out
        cmp reference/err candidate/err
        commands=$((commands + 1))
    done
done
valgrind --error-exitcode=99 --log-file=memcheck.log ./compare --memcheck > memcheck-comparisons.log
grep -q 'ERROR SUMMARY: 0 errors' memcheck.log
cat memcheck-comparisons.log
echo "$commands canonical debugfs commands matched stdout and stderr"
if [ "$release_mode" = --multicall ]; then
    /work/tests/e2fsprogs-dirhash/indexed-image.sh /oracle/stage-gcc/sbin /tmp /tmp/dirhash-images
    PYTHONPATH=/work/scripts python3 -B - "$binary" "$object" "$commands" <<'RECORD'
import json, re, sys
from pathlib import Path
from check_cargo_private_inlines import digest
def comparisons(filename):
    return int(re.fullmatch(r"(\d+) canonical directory hash comparisons passed\n", Path(filename).read_text())[1])
images = [line.split()[0] for line in Path("/tmp/dirhash-images").read_text().splitlines()]
report = {"binary_sha256": digest(Path(sys.argv[1])), "debugfs_archive_sha256": digest(Path(sys.argv[2])),
          "canonical_comparisons": comparisons("compare.log"), "memcheck_comparisons": comparisons("memcheck-comparisons.log"),
          "debugfs_commands": int(sys.argv[3]), "canonical_image_sha256": images[0], "rustbox_image_sha256": images[1]}
Path("/results/dirhash.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
RECORD
fi
CHECK
if [ "${1:-}" = --multicall ]; then
    mv "$scratch/dirhash.json" "$reports/multicall-dirhash.json"
fi
