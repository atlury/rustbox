#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

test "$#" -eq 1 || { echo "usage: $0 BATCH" >&2; exit 2; }
batch=$1
case $batch in *[!A-Za-z0-9_-]*|'') exit 2 ;; esac
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
    output="$build/rustbox-util-linux-small-$suffix"
    cd "$build"
    clang-18 -O2 -g -Wl,-Map,"$output.map" -o "$output" \
      "/work/bridges/util-linux/small-$suffix-dispatch.c" \
      "$library" $extra_objects \
      $extra_libraries -ldl -lpthread -lrt -lutil -lm
    test "$(nm -g --defined-only "$output" | awk '\''/ rustbox_.*_main$/ { count++ } END { print count+0 }'\'')" = 10
    mkdir -p "rustbox-small-$suffix"
    for applet in $applets; do
      ln -sfn "../rustbox-util-linux-small-$suffix" "rustbox-small-$suffix/$applet"
    done
    printf "util-linux hybrid: %s bytes\n" "$(stat -c %s "$output")"
  ' rustbox-util-link \
    "/work/work/analysis/util-linux-2.42.4/translations/c2rust-0.22.1/$batch-stable/target/release/$library_name" \
    "$suffix" "$applets" "$extra_objects" "$extra_libraries"
