#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-procps:2026-11-24 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    source=/work/work/normalized/procps-ng-4.0.7
    volume=/rustbox-procps
    evidence=/work/work/analysis/procps-ng-4.0.7/normalized
    programs="free hugetop kill pgrep pidof pidwait pkill pmap ps pwdx skill slabtop snice sysctl tload top uptime vmstat w watch"

    configure_build()
    {
      compiler=$1
      build=$volume/normalized-$compiler
      rm -rf "$build"
      mkdir -p "$build"
      cd "$build"
      CC="$compiler" CFLAGS="-O2 -g -fno-omit-frame-pointer" \
        "$source/configure" \
          --disable-libselinux --with-systemd=no --with-elogind=no \
          --enable-skill
      bear --output "$evidence/$compiler-compile-commands.json" -- \
        make -j"$(nproc)"
    }

    source_path()
    {
      build=$1
      name=$2
      case "$name" in
        ps) path=$build/src/ps/pscommand ;;
        top) path=$build/src/top/top ;;
        *) path=$build/src/$name ;;
      esac
      payload=$(dirname "$path")/.libs/$(basename "$path")
      if test -x "$payload"; then path=$payload; fi
      printf "%s\n" "$path"
    }

    entrypoint()
    {
      case "$1" in
        pgrep|pkill|pidwait) printf "%s\n" rustbox_procps_pgrep_main ;;
        skill|snice) printf "%s\n" rustbox_procps_skill_main ;;
        *) printf "rustbox_procps_%s_main\n" "$1" ;;
      esac
    }

    publish_programs()
    {
      compiler=$1
      build=$volume/normalized-$compiler
      output=$volume/normalized-programs-$compiler
      rm -rf "$output"
      mkdir -p "$output"
      for name in $programs; do
        path=$(source_path "$build" "$name")
        symbol=$(entrypoint "$name")
        test -x "$path"
        test "$(nm -g --defined-only "$path" | awk -v symbol="$symbol" '\''$NF == symbol { n++ } END { print n+0 }'\'')" -eq 1
        ln -s "$path" "$output/$name"
        readelf -d "$path" >"$evidence/$compiler-$name.dynamic"
        nm -g --defined-only "$path" >"$evidence/$compiler-$name.symbols"
      done
    }

    run_suite()
    {
      compiler=$1
      build=$volume/normalized-$compiler
      set +e
      make -C "$build" check >"$evidence/$compiler-test.log" 2>&1
      status=$?
      set -e
      printf "%s\n" "$status" >"$evidence/$compiler-test.status"
    }

    rm -rf "$evidence"
    mkdir -p "$evidence"
    configure_build gcc >"$evidence/gcc-build.log" 2>&1
    configure_build clang-18 >"$evidence/clang-build.log" 2>&1
    publish_programs gcc
    publish_programs clang-18
    run_suite gcc
    run_suite clang-18
    chmod -R a+rwX "$evidence"
  '
