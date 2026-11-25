#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
set -eu
canon=$1
candidate=$2
export E2FSCK_TIME=1700000000 E2FSPROGS_FAKE_TIME=1700000000 LC_ALL=C TZ=UTC
work=$(mktemp -d)
cd "$work"
mkdir -p tree/many canonical rebuilt
python3 - <<'NAMES'
from pathlib import Path
import os
for index in range(1200):
    (Path("tree/many") / f"{index:04x}-directory-hash-{index % 31:02x}").touch()
for path in [*Path("tree/many").iterdir(), Path("tree/many"), Path("tree")]:
    os.utime(path, (1700000000, 1700000000))
NAMES
truncate -s 32M canonical/fs.img
"$canon/mke2fs" -Fq -t ext4 -b 1024 -O dir_index -U 281d62bd-2720-4681-b8ef-0a85d15430ea \
    -E lazy_itable_init=0,lazy_journal_init=0,hash_seed=4b36d336-9705-4e49-842a-68b364dc1b97 \
    -d tree canonical/fs.img
cp canonical/fs.img rebuilt/fs.img
for variant in canonical rebuilt; do
    (
        cd "$variant"
        tools=$canon
        if [ "$variant" = rebuilt ]; then tools=$candidate; fi
        result=0
        "$tools/e2fsck" -fyD fs.img > check.out 2> check.err || result=$?
        test "$result" -le 1
        echo "$result" > check.status
        "$tools/debugfs" -R 'htree_dump /many' fs.img > tree.out 2> tree.err
        grep -q 'Root node dump:' tree.out
        grep -Eq 'Number of entries \(count\): ([2-9]|[1-9][0-9]+)$' tree.out
    )
done
for file in check.status check.out check.err fs.img tree.out tree.err; do
    cmp "canonical/$file" "rebuilt/$file"
done
if [ "$#" -eq 3 ]; then
    sha256sum canonical/fs.img rebuilt/fs.img > "$3"
fi
echo 'Indexed ext4 directory with 1,200 entries matched canonical e2fsck, debugfs and complete image bytes'
