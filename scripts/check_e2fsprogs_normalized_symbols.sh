#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
exec docker run --rm --platform linux/amd64 \
  --volume "$root:/work" \
  --volume rustbox-e2fsprogs-1.47.4:/rustbox-e2fsprogs \
  --workdir /work rustbox-e2fsprogs:2026-11-24 sh -eu -c '
    evidence=/work/work/analysis/e2fsprogs-1.47.4/normalization
    output=$evidence/symbol-gate.txt
    : >"$output"
    for compiler in gcc clang-18; do
      stage=/rustbox-e2fsprogs/stage-normalized-$compiler
      while read -r name relative; do
        symbol=rustbox_e2fsprogs_${name}_main
        count=$(nm -g --defined-only "$stage/$relative" | awk -v symbol="$symbol" '\''$3 == symbol { count++ } END { print count + 0 }'\'')
        test "$count" -eq 1
        printf "%s %s %s %s\n" "$compiler" "$relative" "$symbol" "$count" >>"$output"
      done <<'\''EOF'\''
badblocks sbin/badblocks
debugfs sbin/debugfs
dumpe2fs sbin/dumpe2fs
e2fsck sbin/e2fsck
e2image sbin/e2image
e2undo sbin/e2undo
fsck sbin/fsck
logsave sbin/logsave
mke2fs sbin/mke2fs
resize2fs sbin/resize2fs
tune2fs sbin/tune2fs
chattr usr/bin/chattr
fuse2fs usr/bin/fuse2fs
lsattr usr/bin/lsattr
e2initrd_helper usr/lib/e2initrd_helper
e2freefrag usr/sbin/e2freefrag
e4crypt usr/sbin/e4crypt
e4defrag usr/sbin/e4defrag
filefrag usr/sbin/filefrag
mklost_found usr/sbin/mklost+found
EOF
    done
    test "$(wc -l <"$output")" -eq 40
    chmod a+rw "$output"
  '
