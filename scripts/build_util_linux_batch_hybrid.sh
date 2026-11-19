#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

test "$#" -eq 1 || { echo "usage: $0 BATCH" >&2; exit 2; }
batch=$1
case $batch in *[!A-Za-z0-9_-]*|'') exit 2 ;; esac
replacement_count=10
case $batch in
  util-linux-small-01)
    suffix=01
    library_name=libutil_linux_small_01_normalized_reachable.a
    applets='line setpgid exch ctrlaltdel setsid choom fadvise colrm mcookie rev'
    extra_objects='lib/md5.o ./.libs/libcommon.a'
    extra_libraries=''
    ;;
  util-linux-small-02)
    suffix=02
    library_name=libutil_linux_small_02_normalized_reachable.a
    applets='pivot_root delpart addpart findfs nologin resizepart mkfs fsfreeze isosize mesg'
    extra_objects='./.libs/libblkid.a ./.libs/libcommon.a'
    extra_libraries='-leconf'
    ;;
  util-linux-small-03)
    suffix=03
    library_name=libutil_linux_small_03_normalized_reachable.a
    applets='swaplabel lsirq newgrp uuidgen switch_root raw renice ionice fdformat copyfilerange'
    extra_objects='lib/swaplabel-swapprober.o sys-utils/lsirq-irq-common.o ./.libs/libblkid.a ./.libs/libsmartcols.a ./.libs/libuuid.a ./.libs/libcommon.a'
    extra_libraries='-leconf -lcrypt'
    ;;
  util-linux-small-04)
    suffix=04
    library_name=libutil_linux_small_04_normalized_reachable.a
    applets='taskset mountpoint chsh waitpid colcrt getino ipcmk bits swapoff uclampset'
    extra_objects='login-utils/chsh-ch-common.o login-utils/chsh-auth.o login-utils/chsh-islocal.o login-utils/chsh-setpwnam.o sys-utils/swapoff-swapon-common.o lib/swapoff-swapprober.o ./.libs/libmount.a ./.libs/libblkid.a ./.libs/libcommon_logindefs.a ./.libs/libcommon_shells.a ./.libs/libcommon.a'
    extra_libraries='-leconf -lpam -lpam_misc'
    ;;
  util-linux-small-05)
    suffix=05
    library_name=libutil_linux_small_05_normalized_reachable.a
    applets='look pipesz blkdiscard tunelp rename uuidparse utmpdump lastlog2 scriptlive vipw'
    extra_objects='lib/blkdiscard-monotonic.o lib/lastlog2-strutils.o term-utils/script-playutils.o lib/pty-session.o ./.libs/liblastlog2.a ./.libs/libblkid.a ./.libs/libsmartcols.a ./.libs/libuuid.a ./.libs/libcommon.a'
    extra_libraries='-leconf -lsqlite3'
    ;;
  util-linux-small-06)
    suffix=06
    library_name=libutil_linux_small_06_normalized_reachable.a
    applets='coresched chcpu namei wall readprofile scriptreplay blkpr ldattach blockdev flock'
    extra_objects='lib/strutils.o lib/idcache.o term-utils/wall-ttymsg.o term-utils/script-playutils.o lib/monotonic.o lib/timer.o ./.libs/libcommon.a'
    extra_libraries=''
    ;;
  util-linux-small-07)
    suffix=07
    library_name=libutil_linux_small_07_normalized_reachable.a
    applets='mkfs.bfs write getopt fallocate chrt fincore whereis col chmem rfkill'
    extra_objects='./.libs/libsmartcols.a ./.libs/libcommon.a'
    extra_libraries=''
    ;;
  util-linux-small-08)
    suffix=08
    library_name=libutil_linux_small_08_normalized_reachable.a
    applets='i386 ia64 linux32 linux64 mips mips32 mips64 parisc parisc32 parisc64 ppc ppc32 ppc64 s390 s390x setarch sparc sparc32 sparc32bash sparc64 uname26 x86_64'
    extra_objects='./.libs/libcommon.a'
    extra_libraries=''
    replacement_count=1
    ;;
  util-linux-small-09)
    suffix=09
    library_name=libutil_linux_small_09_normalized_reachable.a
    applets='blkzone ipcrm fstrim prlimit fsck.cramfs mkfs.cramfs kill rtcwake wdctl ul'
    extra_objects='sys-utils/ipcutils.o disk-utils/cramfs_common.o ./.libs/libmount.a ./.libs/libblkid.a ./.libs/libsmartcols.a ./.libs/libcommon.a'
    extra_libraries='-leconf -lz -ltinfo'
    ;;
  util-linux-small-10)
    suffix=10
    library_name=libutil_linux_small_10_normalized_reachable.a
    applets='enosys ipcs last lastb lsclocks lslocks lsmem mkfs.minix mkswap setterm uuidd'
    extra_objects='sys-utils/ipcutils.o lib/ismounted.o lib/monotonic.o lib/uuidd-timer.o ./.libs/libmount.a ./.libs/libblkid.a ./.libs/libsmartcols.a ./.libs/libuuid.a ./.libs/libcommon.a'
    extra_libraries='-leconf -ltinfo'
    ;;
  util-linux-small-11)
    suffix=11
    library_name=libutil_linux_small_11_normalized_reachable.a
    applets='blkid column eject logger losetup nsenter partx setpriv wipefs zramctl'
    extra_objects='lib/ismounted.o lib/monotonic.o lib/logger-strutils.o lib/logger-strv.o lib/exec_shell.o lib/caputils.o sys-utils/setpriv-landlock.o ./.libs/libmount.a ./.libs/libblkid.a ./.libs/libsmartcols.a ./.libs/libtcolors.a ./.libs/libcommon_logindefs.a ./.libs/libcommon.a'
    extra_libraries='-leconf -lcap-ng -ltinfo'
    ;;
  util-linux-small-12)
    suffix=12
    library_name=libutil_linux_small_12_normalized_reachable.a
    applets='cal dmesg fsck.minix hardlink irqtop lsipc more mount pg umount'
    extra_objects='lib/monotonic.o lib/dmesg-pager.o lib/ismounted.o lib/hardlink-fileeq.o sys-utils/lsirq-irq-common.o sys-utils/ipcutils.o ./.libs/libmount.a ./.libs/libblkid.a ./.libs/libsmartcols.a ./.libs/libtcolors.a ./.libs/libcommon.a'
    extra_libraries='-leconf -lmagic -lncursesw -ltinfo'
    ;;
  util-linux-small-13)
    suffix=13
    library_name=libutil_linux_small_13_normalized_reachable.a
    applets='chfn fsck hexdump hwclock lscpu lslogins lsns script swapon unshare'
    extra_objects='login-utils/chfn-ch-common.o login-utils/chfn-auth.o login-utils/chfn-islocal.o login-utils/chfn-setpwnam.o lib/monotonic.o text-utils/hexdump-conv.o text-utils/hexdump-display.o text-utils/hexdump-parse.o rustbox-support-13/hwclock-parse-date.o sys-utils/hwclock-hwclock-cmos.o sys-utils/hwclock-hwclock-rtc.o sys-utils/lscpu-lscpu-cputype.o sys-utils/lscpu-lscpu-cpu.o sys-utils/lscpu-lscpu-topology.o sys-utils/lscpu-lscpu-virt.o sys-utils/lscpu-lscpu-arm.o sys-utils/lscpu-lscpu-dmi.o sys-utils/lscpu-lscpu-riscv.o lib/script-pty-session.o sys-utils/swapon-swapon-common.o lib/swapon-swapprober.o lib/unshare-caputils.o lib/unshare-exec_shell.o ./.libs/liblastlog2.a ./.libs/libmount.a ./.libs/libblkid.a ./.libs/libsmartcols.a ./.libs/libtcolors.a ./.libs/libcommon_logindefs.a ./.libs/libcommon.a'
    extra_libraries='-leconf -lpam -lpam_misc -lsqlite3 -ltinfo'
    ;;
  util-linux-small-14)
    suffix=14
    library_name=libutil_linux_small_14_normalized_reachable.a
    applets='agetty cfdisk fdisk findmnt login lsblk lsfd runuser sfdisk su sulogin vigr'
    extra_objects='lib/agetty-plymouth-ctrl.o lib/agetty-netlink.o lib/agetty-netaddrq.o disk-utils/fdisk-fdisk-menu.o disk-utils/fdisk-fdisk-list.o lib/fdisk-pager.o misc-utils/findmnt-findmnt-verify.o misc-utils/lsblk-lsblk-mnt.o misc-utils/lsblk-lsblk-properties.o misc-utils/lsblk-lsblk-devtree.o lsfd-cmd/lsfd-decode-file-flags.o lsfd-cmd/lsfd-file.o lsfd-cmd/lsfd-error.o lsfd-cmd/lsfd-cdev.o lsfd-cmd/lsfd-bdev.o lsfd-cmd/lsfd-sock.o lsfd-cmd/lsfd-sock-xinfo.o lsfd-cmd/lsfd-unkn.o lsfd-cmd/lsfd-fifo.o lsfd-cmd/lsfd-pidfd.o lsfd-cmd/lsfd-util.o login-utils/su-common.o lib/pty-session.o lib/monotonic.o login-utils/sulogin-consoles.o rustbox-support-14/list-sort-support.o ./.libs/libfdisk.a ./.libs/libmount.a ./.libs/libblkid.a ./.libs/libsmartcols.a ./.libs/libtcolors.a ./.libs/libuuid.a ./.libs/libcommon_logindefs.a ./.libs/libcommon_shells.a ./.libs/libcommon.a'
    extra_libraries='-leconf -lcrypt -lncursesw -lpam -lpam_misc -lreadline -ltinfo'
    replacement_count=12
    ;;
  *) echo "hybrid linker not yet declared for $batch" >&2; exit 2 ;;
esac

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
stable="$root/work/analysis/util-linux-2.42.4/translations/c2rust-0.22.1/$batch-stable"
library="$stable/target/release/$library_name"
test -s "$library" || { echo "build the stable Rust crate first" >&2; exit 1; }

RUSTBOX_TOOL_IMAGE=rustbox-normalize:2026-11-19 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    build=/rustbox-util-linux/canonical-clang-compdb
    library=$1
    suffix=$2
    applets=$3
    extra_objects=$4
    extra_libraries=$5
    replacement_count=$6
    output="$build/rustbox-util-linux-small-$suffix"
    cd "$build"
    if test "$suffix" = 13; then
      mkdir -p rustbox-support-13
      cp sys-utils/hwclock-hwclock-parse-date.o rustbox-support-13/hwclock-parse-date.o
      objcopy --redefine-sym yyparse=rustbox_hwclock_yyparse \
        rustbox-support-13/hwclock-parse-date.o
      nm -g --defined-only rustbox-support-13/hwclock-parse-date.o \
        | grep -q " rustbox_hwclock_yyparse$"
    fi
    if test "$suffix" = 14; then
      mkdir -p rustbox-support-14
      clang-18 -O2 -g -DHAVE_CONFIG_H -I. -include config.h \
        -I/rustbox-util-linux-source/util-linux-2.42.4/include \
        -c /work/bridges/util-linux/list-sort-support.c \
        -o rustbox-support-14/list-sort-support.o
    fi
    clang-18 -O2 -g -Wl,-Map,"$output.map" -o "$output" \
      "/work/bridges/util-linux/small-$suffix-dispatch.c" \
      "$library" $extra_objects \
      $extra_libraries -ldl -lpthread -lrt -lutil -lm
    test "$(nm -g --defined-only "$output" | awk '\''/ rustbox_.*_main$/ { count++ } END { print count+0 }'\'')" = "$replacement_count"
    mkdir -p "rustbox-small-$suffix"
    for applet in $applets; do
      ln -sfn "../rustbox-util-linux-small-$suffix" "rustbox-small-$suffix/$applet"
    done
    printf "util-linux hybrid: %s bytes\n" "$(stat -c %s "$output")"
  ' rustbox-util-link \
    "/work/work/analysis/util-linux-2.42.4/translations/c2rust-0.22.1/$batch-stable/target/release/$library_name" \
    "$suffix" "$applets" "$extra_objects" "$extra_libraries" "$replacement_count"
