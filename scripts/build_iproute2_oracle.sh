#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-iproute2:2026-11-24 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    source=/work/work/upstream/iproute2-7.3.0
    volume=/rustbox-iproute2
    evidence=/work/work/analysis/iproute2-7.3.0/oracle
    programs="arpd bridge ctstat dcb devlink dpll genl ifstat ip lnstat netshaper nstat rdma routel rtacct rtmon rtstat ss tc tipc vdpa"

    configure_build()
    {
      compiler=$1
      build=$volume/oracle-$compiler
      rm -rf "$build"
      cp -a "$source" "$build"
      cd "$build"
      PKG_CONFIG=/work/tools/iproute2-pkg-config \
      CC="$compiler" HOSTCC="$compiler" \
      CFLAGS="-O2 -g -fno-omit-frame-pointer" \
        ./configure --libbpf_force=on
      bear --output "$evidence/$compiler-compile-commands.json" -- \
        make -j"$(nproc)" SHARED_LIBS=n CC="$compiler" HOSTCC="$compiler"
    }

    publish_programs()
    {
      compiler=$1
      build=$volume/oracle-$compiler
      output=$volume/programs-$compiler
      rm -rf "$output"
      mkdir -p "$output"
      for name in $programs; do
        case "$name" in
          arpd|ifstat|lnstat|nstat|rtacct|ss) path=$build/misc/$name ;;
          ctstat|rtstat) path=$build/misc/lnstat ;;
          bridge) path=$build/bridge/bridge ;;
          dcb) path=$build/dcb/dcb ;;
          devlink) path=$build/devlink/devlink ;;
          dpll) path=$build/dpll/dpll ;;
          genl) path=$build/genl/genl ;;
          ip|rtmon|routel) path=$build/ip/$name ;;
          netshaper) path=$build/netshaper/netshaper ;;
          rdma) path=$build/rdma/rdma ;;
          tc) path=$build/tc/tc ;;
          tipc) path=$build/tipc/tipc ;;
          vdpa) path=$build/vdpa/vdpa ;;
          *) echo "unknown IPRoute2 program: $name" >&2; exit 1 ;;
        esac
        test -x "$path"
        ln -s "$path" "$output/$name"
        if file "$path" | grep -q ELF; then
          readelf -d "$path" >"$evidence/$compiler-$name.dynamic"
        else
          printf "script\n" >"$evidence/$compiler-$name.dynamic"
        fi
      done
    }

    run_suite()
    {
      compiler=$1
      build=$volume/oracle-$compiler
      set +e
      make -C "$build" SHARED_LIBS=n check >"$evidence/$compiler-test.log" 2>&1
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
