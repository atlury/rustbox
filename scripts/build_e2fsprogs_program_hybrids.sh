#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
exec docker run --rm --platform linux/amd64 \
  --volume "$root:/work" \
  --volume rustbox-e2fsprogs-1.47.4:/rustbox-e2fsprogs \
  --workdir /work rustbox-e2fsprogs:2026-11-24 sh -eu -c '
    base=/work/work/analysis/e2fsprogs-1.47.4/program-translations
    output=/rustbox-e2fsprogs/program-hybrids
    evidence=/work/work/analysis/e2fsprogs-1.47.4/program-hybrids
    programs="badblocks chattr debugfs dumpe2fs e2freefrag e2fsck e2image e2initrd_helper e2undo e4crypt e4defrag filefrag fsck fuse2fs logsave lsattr mke2fs mklost_found resize2fs tune2fs"

    missing=0
    for name in $programs; do
      archive=$base/cargo-target/$name/release/lib${name}_audit.a
      check=$base/$name/$name-final/rustbox-cargo-check.json
      if [ ! -f "$archive" ] || [ ! -f "$check" ]; then
        echo "missing translated E2fsprogs artifact: $name" >&2
        missing=1
      fi
    done
    test "$missing" -eq 0

    rm -rf "$output" "$evidence"
    mkdir -p "$output" "$evidence"
    for name in $programs; do
      archive=$base/cargo-target/$name/release/lib${name}_audit.a
      check=$base/$name/$name-final/rustbox-cargo-check.json
      python3 - "$check" <<'\''PY'\''
import json, sys
record = json.load(open(sys.argv[1]))
assert record["exit_status"] == 0
assert record["build_finished_success"] is True
assert not record["errors"]
PY
      clang-18 -O2 -g -fno-omit-frame-pointer \
        -ffunction-sections -fdata-sections -Wl,--gc-sections \
        -Wl,-Map,"$evidence/$name.map" \
        -DRUSTBOX_E2FSPROGS_ENTRY=rustbox_e2fsprogs_${name}_main \
        -o "$output/$name" /work/bridges/e2fsprogs_program_main.c \
        "$archive" \
        -lblkid -luuid -lfuse3 -ldl -lpthread -lm
      nm -g --defined-only "$output/$name" >"$evidence/$name.symbols"
      test "$(awk -v symbol="rustbox_e2fsprogs_${name}_main" \
        '\''$NF == symbol { n++ } END { print n+0 }'\'' \
        "$evidence/$name.symbols")" -eq 1
    done

    ln -s tune2fs "$output/e2label"
    ln -s dumpe2fs "$output/e2mmpstatus"
    for name in fsck.ext2 fsck.ext3 fsck.ext4; do ln -s e2fsck "$output/$name"; done
    for name in mkfs.ext2 mkfs.ext3 mkfs.ext4; do ln -s mke2fs "$output/$name"; done
    ln -s mklost_found "$output/mklost+found"
    chmod -R a+rwX "$output" "$evidence"
  '
