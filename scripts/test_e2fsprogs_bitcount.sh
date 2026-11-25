#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
set -eu
case "$#:$*" in
    0:|1:--multicall) ;;
    *) echo "usage: $0 [--multicall]" >&2; exit 2 ;;
esac
root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
reports="$root/work/analysis/e2fsprogs-1.47.4"
scratch=$(mktemp -d "$reports/bitcount-test.XXXXXXXX")
trap 'rm -rf "$scratch"' EXIT
docker run --rm -i --network none --platform linux/amd64 \
    -v "$scratch:/results" -v "$root:/work:ro" -v rustbox-e2fsprogs-1.47.4:/oracle:ro \
    -v rustbox-coreutils-9.12:/rustbox-coreutils:ro \
    --workdir /tmp rustbox-e2fsprogs:2026-11-24 sh -seu -- "$@" <<'CHECK'
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
engines=/work/work/analysis/e2fsprogs-1.47.4/program-translations/rustbox-e2fsprogs-shared
canon=/oracle/stage-gcc/sbin
if [ "${1:-}" = --multicall ]; then
    binary=/rustbox-coreutils/canonical-clang-no-security-compdb/src/rustbox
    object=$engines/bitcount.o
    python3 - "$binary" "$object" <<'VERIFY'
import hashlib, json, sys
from pathlib import Path
link = json.loads(Path("/work/work/analysis/rustbox-multicall-link.json").read_bytes())
for path, expected in zip(map(Path, sys.argv[1:]), (
        link["binary"]["sha256"], link["e2fsprogs_shared_bitcount"]["object_sha256"])):
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise SystemExit(f"{path} differs from the recorded multicall release")
VERIFY
    for name in e2fsck resize2fs; do ln -s "$binary" "/tmp/$name"; done
else
    object=/tmp/candidate.o
    rustc --edition=2021 --crate-type=lib --emit=obj -C opt-level=s -C panic=abort \
        /work/compat/e2fsprogs/bitcount.rs -o "$object"
    for name in e2fsck resize2fs; do
        clang-18 -O2 -Wl,--gc-sections \
            "-DRUSTBOX_E2FSPROGS_ENTRY=rustbox_e2fsprogs_${name}_main" \
            /work/bridges/e2fsprogs_program_main.c "$engines/$name/lib${name}_audit.a" \
            "$engines/crc16.o" "$engines/crc32.o" "$object" \
            -lblkid -luuid -lfuse3 -ldl -lpthread -lm -o "/tmp/$name"
    done
fi
gcc -Wall -Wextra -Werror -O2 /work/tests/e2fsprogs-bitcount/differential.c \
    canonical.o "$object" -o compare
./compare > compare.log
cat compare.log
export E2FSCK_TIME=1700000000 E2FSPROGS_FAKE_TIME=1700000000
mkdir reference candidate memcheck
truncate -s 32M reference/fs.img
"$canon/mke2fs" -Fq -t ext4 -b 1024 -E lazy_itable_init=0,lazy_journal_init=0 reference/fs.img
cp reference/fs.img candidate/fs.img
cp reference/fs.img memcheck/fs.img
for variant in reference candidate memcheck; do
    (
        cd "$variant"
        check() {
            name=$1
            shift
            if [ "$variant" = reference ]; then
                "$canon/$name" "$@"
            elif [ "$variant" = memcheck ]; then
                valgrind --tool=memcheck --error-exitcode=99 --leak-check=no \
                    --track-origins=yes --log-file="$name.log" "/tmp/$name" "$@"
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
    cmp "reference/$file" "memcheck/$file"
done
for name in e2fsck resize2fs; do
    grep -Eq '^(c?fn)=.*rustbox_e2fsprogs_bitcount$' "candidate/$name.calls"
    grep -q "ERROR SUMMARY: 0 errors" "memcheck/$name.log"
    echo "$name exercised the replacement, matched the canonical image run and passed Memcheck"
done
if [ "${1:-}" = --multicall ]; then
    python3 - "$binary" "$object" <<'RECORD'
import hashlib, json, re, sys
from pathlib import Path
def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
image = Path("candidate/fs.img")
report = {
    "binary_sha256": sha(sys.argv[1]),
    "object_sha256": sha(sys.argv[2]),
    "canonical_comparisons": int(re.fullmatch(
        r"(\d+) canonical bitmap count comparisons passed, including uint32 wraparound\n",
        Path("compare.log").read_text()).group(1)),
    "traced_callers": ["e2fsck", "resize2fs"],
    "memcheck_errors": {name: int(re.search(r"ERROR SUMMARY: (\d+) errors",
        Path(f"memcheck/{name}.log").read_text()).group(1)) for name in ("e2fsck", "resize2fs")},
    "canonical_image_sha256": sha("reference/fs.img"),
    "rustbox_image_sha256": sha(image),
    "grown_image_bytes": image.stat().st_size,
}
Path("/results/bitcount.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
RECORD
fi
CHECK
if [ "${1:-}" = --multicall ]; then
    mv "$scratch/bitcount.json" "$reports/multicall-bitcount.json"
fi
