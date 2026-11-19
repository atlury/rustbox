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
