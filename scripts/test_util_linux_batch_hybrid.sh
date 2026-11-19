#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

test "$#" -eq 1 || { echo "usage: $0 BATCH" >&2; exit 2; }
batch=$1
case $batch in
  util-linux-small-01) suffix=01; components='line setpgid exch setsid choom fadvise colrm mcookie rev'; count=9 ;;
  util-linux-small-02) suffix=02; components='isosize'; count=1 ;;
  util-linux-small-03) suffix=03; components='swaplabel uuidgen ionice copyfilerange'; count=5 ;;
  util-linux-small-04) suffix=04; components='bits colcrt getino mountpoint waitpid'; count=7 ;;
  util-linux-small-05) suffix=05; components='blkdiscard look pipesz rename uuidparse'; count=10 ;;
  util-linux-small-06) suffix=06; components='coresched flock namei'; count=4 ;;
  util-linux-small-07) suffix=07; components='chrt col fallocate fincore getopt whereis'; count=11 ;;
  util-linux-small-08) suffix=08; components='setarch'; count=3 ;;
  util-linux-small-09) suffix=09; components='kill ul'; count=9 ;;
  util-linux-small-10) suffix=10; components='enosys ipcs lsclocks lslocks lsmem mkswap uuidd utmp'; count=21 ;;
  util-linux-small-11) suffix=11; components='blkid column eject logger losetup nsenter partx setpriv wipefs'; count=31 ;;
  util-linux-small-12) suffix=12; components='cal dmesg hardlink more mount'; count=66 ;;
  util-linux-small-13) suffix=13; components='chfn fsck hexdump hwclock lscpu lslogins lsns script swapon unshare'; count=29 ;;
  *) echo "unknown batch: $batch" >&2; exit 2 ;;
esac

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
exec "$root/scripts/run_tool.sh" sh -eu -c '
  source=/rustbox-util-linux-source/util-linux-2.42.4
  build=/rustbox-util-linux/canonical-clang-compdb
  suffix=$1
  components=$2
  count=$3
  stable="/work/work/analysis/util-linux-2.42.4/translations/c2rust-0.22.1/util-linux-small-$suffix-stable"
  hybrid="$build/rustbox-util-linux-small-$suffix"
  test -x "$hybrid"
  python3 "/work/tests/util-linux-small-$suffix-differential.py" \
    --canonical-directory "$build" \
    --hybrid "$hybrid" \
    --output "$stable/differential.json"

  cd "$build"
  if test "$suffix" = 01; then make -j"$(nproc)" test_md5; fi
  if test "$suffix" = 03; then make -j"$(nproc)" test_sysinfo test_uuid_parser; fi
  if test "$suffix" = 04; then make -j"$(nproc)" test_strerror; fi
  if test "$suffix" = 05; then make -j"$(nproc)" test_uuid_time; fi
  chmod -R a+rwX "$build"
  getent passwd rustbox-test >/dev/null || useradd -m rustbox-test
  if test "$suffix" = 01; then
    export TS_CMD_LINE="$build/rustbox-small-01/line"
    export TS_CMD_SETPGID="$build/rustbox-small-01/setpgid"
    export TS_CMD_EXCH="$build/rustbox-small-01/exch"
    export TS_CMD_SETSID="$build/rustbox-small-01/setsid"
    export TS_CMD_CHOOM="$build/rustbox-small-01/choom"
    export TS_CMD_FADVISE="$build/rustbox-small-01/fadvise"
    export TS_CMD_COLRM="$build/rustbox-small-01/colrm"
    export TS_CMD_MCOOKIE="$build/rustbox-small-01/mcookie"
    export TS_CMD_REV="$build/rustbox-small-01/rev"
  elif test "$suffix" = 02; then
    export TS_CMD_ISOSIZE="$build/rustbox-small-02/isosize"
  elif test "$suffix" = 03; then
    export TS_CMD_SWAPLABEL="$build/rustbox-small-03/swaplabel"
    export TS_CMD_UUIDGEN="$build/rustbox-small-03/uuidgen"
    export TS_CMD_IONICE="$build/rustbox-small-03/ionice"
    export TS_CMD_COPYFILERANGE="$build/rustbox-small-03/copyfilerange"
  elif test "$suffix" = 04; then
    export TS_CMD_BITS="$build/rustbox-small-04/bits"
    export TS_CMD_COLCRT="$build/rustbox-small-04/colcrt"
    export TS_CMD_GETINO="$build/rustbox-small-04/getino"
    export TS_CMD_MOUNTPOINT="$build/rustbox-small-04/mountpoint"
    export TS_CMD_WAITPID="$build/rustbox-small-04/waitpid"
  elif test "$suffix" = 05; then
    export TS_CMD_BLKDISCARD="$build/rustbox-small-05/blkdiscard"
    export TS_CMD_LOOK="$build/rustbox-small-05/look"
    export TS_CMD_PIPESZ="$build/rustbox-small-05/pipesz"
    export TS_CMD_RENAME="$build/rustbox-small-05/rename"
    export TS_CMD_UUIDPARSE="$build/rustbox-small-05/uuidparse"
  elif test "$suffix" = 06; then
    export TS_CMD_CORESCHED="$build/rustbox-small-06/coresched"
    export TS_CMD_FLOCK="$build/rustbox-small-06/flock"
    export TS_CMD_NAMEI="$build/rustbox-small-06/namei"
  elif test "$suffix" = 07; then
    export TS_CMD_CHRT="$build/rustbox-small-07/chrt"
    export TS_CMD_COL="$build/rustbox-small-07/col"
    export TS_CMD_FALLOCATE="$build/rustbox-small-07/fallocate"
    export TS_CMD_FINCORE="$build/rustbox-small-07/fincore"
    export TS_CMD_GETOPT="$build/rustbox-small-07/getopt"
    export TS_CMD_WHEREIS="$build/rustbox-small-07/whereis"
  elif test "$suffix" = 08; then
    export TS_CMD_SETARCH="$build/rustbox-small-08/setarch"
  elif test "$suffix" = 09; then
    export TS_CMD_KILL="$build/rustbox-small-09/kill"
    export TS_CMD_UL="$build/rustbox-small-09/ul"
  elif test "$suffix" = 10; then
    export TS_CMD_ENOSYS="$build/rustbox-small-10/enosys"
    export TS_CMD_IPCS="$build/rustbox-small-10/ipcs"
    export TS_CMD_LAST="$build/rustbox-small-10/last"
    export TS_CMD_LSCLOCKS="$build/rustbox-small-10/lsclocks"
    export TS_CMD_LSLOCKS="$build/rustbox-small-10/lslocks"
    export TS_CMD_LSMEM="$build/rustbox-small-10/lsmem"
    export TS_CMD_MKSWAP="$build/rustbox-small-10/mkswap"
    export TS_CMD_UUIDD="$build/rustbox-small-10/uuidd"
  elif test "$suffix" = 11; then
    export TS_CMD_BLKID="$build/rustbox-small-11/blkid"
    export TS_CMD_COLUMN="$build/rustbox-small-11/column"
    export TS_CMD_EJECT="$build/rustbox-small-11/eject"
    export TS_CMD_LOGGER="$build/rustbox-small-11/logger"
    export TS_CMD_LOSETUP="$build/rustbox-small-11/losetup"
    export TS_CMD_NSENTER="$build/rustbox-small-11/nsenter"
    export TS_CMD_PARTX="$build/rustbox-small-11/partx"
    export TS_CMD_SETPRIV="$build/rustbox-small-11/setpriv"
    export TS_CMD_WIPEFS="$build/rustbox-small-11/wipefs"
    export TS_CMD_ZRAMCTL="$build/rustbox-small-11/zramctl"
  elif test "$suffix" = 12; then
    export TS_CMD_CAL="$build/rustbox-small-12/cal"
    export TS_CMD_DMESG="$build/rustbox-small-12/dmesg"
    export TS_CMD_FSCK_MINIX="$build/rustbox-small-12/fsck.minix"
    export TS_CMD_HARDLINK="$build/rustbox-small-12/hardlink"
    export TS_CMD_IRQTOP="$build/rustbox-small-12/irqtop"
    export TS_CMD_LSIPC="$build/rustbox-small-12/lsipc"
    export TS_CMD_MORE="$build/rustbox-small-12/more"
    export TS_CMD_MOUNT="$build/rustbox-small-12/mount"
    export TS_CMD_PG="$build/rustbox-small-12/pg"
    export TS_CMD_UMOUNT="$build/rustbox-small-12/umount"
  else
    export TS_CMD_CHFN="$build/rustbox-small-13/chfn"
    export TS_CMD_FSCK="$build/rustbox-small-13/fsck"
    export TS_CMD_HEXDUMP="$build/rustbox-small-13/hexdump"
    export TS_CMD_HWCLOCK="$build/rustbox-small-13/hwclock"
    export TS_CMD_LSCPU="$build/rustbox-small-13/lscpu"
    export TS_CMD_LSLOGINS="$build/rustbox-small-13/lslogins"
    export TS_CMD_LSNS="$build/rustbox-small-13/lsns"
    export TS_CMD_SCRIPT="$build/rustbox-small-13/script"
    export TS_CMD_SWAPON="$build/rustbox-small-13/swapon"
    export TS_CMD_UNSHARE="$build/rustbox-small-13/unshare"
  fi
  su -m -s /bin/bash rustbox-test -c \
    "cd $build && $source/tests/run.sh --srcdir=$source --builddir=$build $components" \
    | tee "$stable/upstream-targeted.log"
  grep -q "All $count tests PASSED" "$stable/upstream-targeted.log"
' rustbox-util-test "$suffix" "$components" "$count"
