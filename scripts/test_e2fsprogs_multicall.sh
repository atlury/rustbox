#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
set -eu

if [ "$#" -gt 1 ]; then
    echo "usage: $0 [candidate-binary]" >&2
    exit 2
fi
root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
exec "$root/scripts/run_multicall_tool.sh" sh -eu -c '
    rustbox=${1:-${RUSTBOX_TEST_ELF:-/rustbox-coreutils/canonical-clang-no-security-compdb/src/rustbox}}
    canonical=/rustbox-e2fsprogs/stage-gcc
    source=/work/work/upstream/e2fsprogs-1.47.4
    output=/work/work/analysis/e2fsprogs-1.47.4/multicall
    if [ "$#" -eq 1 ]; then output=$output-candidate; fi
    dispatch=$output/dispatch
    test -x "$rustbox"
    test -x "$canonical/sbin/e2fsck"
    rm -rf "$output"
    mkdir -p "$dispatch"
    for name in e2scrub e2scrub_all compile_et mk_cmds; do
      ln -s "$rustbox" "$dispatch/$name"
    done

    python3 -B /work/tests/e2fsprogs-multicall-differential.py \
      --canonical-root "$canonical" --rustbox "$rustbox" \
      --output "$output/differential.json"
    python3 -B /work/tests/e2fsprogs-script-frontends.py \
      --canonical-root "$canonical" --native "$dispatch" --source "$source" \
      --output "$output/frontend-differential.json"

    # Reuse the canonical fake-LVM contract so no real block device is touched.
    mock=/usr/local/sbin/rustbox-e2fs-mock
    printf "%s\n" \
      "#!/bin/sh" \
      "name=\${0##*/}" \
      "case \"\$name\" in" \
      "  lsblk)" \
      "    case \"\$*\" in" \
      "      *NAME,FSTYPE,MOUNTPOINT*) echo '\''NAME=\"/dev/rustbox-vg/rustbox-lv\" FSTYPE=\"ext4\" MOUNTPOINT=\"/mnt/rustbox-e2scrub-test\"'\'' ;;" \
      "      *NAME,MOUNTPOINT,FSTYPE,TYPE*) echo '\''NAME=\"/dev/rustbox-vg/rustbox-lv\" MOUNTPOINT=\"/mnt/rustbox-e2scrub-test\" FSTYPE=\"ext4\" TYPE=\"lvm\"'\'' ;;" \
      "    esac ;;" \
      "  dumpe2fs) echo '\''Filesystem features: has_journal extent'\'' ;;" \
      "  lvs)" \
      "    case \"\$*\" in" \
      "      *--nameprefixes*) echo \"LVM2_LV_NAME='\''rustbox-lv'\'' LVM2_VG_NAME='\''rustbox-vg'\'' LVM2_LV_ROLE='\''public'\''\" ;;" \
      "      *lv_role=snapshot*) echo '\''/dev/rustbox-vg/rustbox-lv.e2scrub'\'' ;;" \
      "      *lv_snapshot_invalid*) : ;;" \
      "      *) echo '\''/dev/rustbox-vg/rustbox-lv'\'' ;;" \
      "    esac ;;" \
      "  *) exit 0 ;;" \
      "esac" >"$mock"
    chmod 755 "$mock"
    for name in lsblk lvs lvcreate lvremove udevadm dumpe2fs; do
      ln -sf rustbox-e2fs-mock "/usr/local/sbin/$name"
    done
    mkdir -p /mnt/rustbox-e2scrub-test /dev/rustbox-vg
    : >/dev/rustbox-vg/rustbox-lv
    RUSTBOX_E2FSPROGS_TEST_EXTERNAL_COMMANDS=1 \
      python3 -B /work/tests/e2fsprogs-script-frontends.py --lvm-only \
      --canonical-root "$canonical" --native "$dispatch" --source "$source" \
      --output "$output/lvm-differential.json"

    while read -r public dispatch_name; do
      valgrind --leak-check=full --show-leak-kinds=all \
        --errors-for-leak-kinds=definite,indirect,possible \
        --log-file="$output/valgrind-$public.log" \
        "$rustbox" "$dispatch_name" --help \
        >"$output/valgrind-$public.out" 2>&1 || true
      grep -q "ERROR SUMMARY: 0 errors" "$output/valgrind-$public.log"
      if ! grep -q "All heap blocks were freed -- no leaks are possible" \
          "$output/valgrind-$public.log"; then
        grep -q "definitely lost: 0 bytes" "$output/valgrind-$public.log"
        grep -q "indirectly lost: 0 bytes" "$output/valgrind-$public.log"
        grep -q "possibly lost: 0 bytes" "$output/valgrind-$public.log"
      fi
    done <<'\''EOF'\''
badblocks badblocks
chattr chattr
compile_et compile_et
debugfs debugfs
dumpe2fs dumpe2fs
e2freefrag e2freefrag
e2fsck e2fsck
e2image e2image
e2initrd_helper e2initrd_helper
e2label e2label
e2mmpstatus e2mmpstatus
e2scrub e2scrub
e2scrub_all e2scrub_all
e2undo e2undo
e4crypt e4crypt
e4defrag e4defrag
filefrag filefrag
e2fsprogs-fsck e2fsprogs-fsck
fsck.ext2 fsck.ext2
fsck.ext3 fsck.ext3
fsck.ext4 fsck.ext4
fuse2fs fuse2fs
logsave logsave
lsattr lsattr
mk_cmds mk_cmds
mke2fs mke2fs
mkfs.ext2 mkfs.ext2
mkfs.ext3 mkfs.ext3
mkfs.ext4 mkfs.ext4
mklost+found mklost+found
resize2fs resize2fs
tune2fs tune2fs
EOF
    test "$(find "$output" -name "valgrind-*.log" -type f | wc -l)" -eq 32
    chmod -R a+rwX "$output"
  ' sh "$@"
