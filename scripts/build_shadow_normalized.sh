#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-shadow:2026-11-24 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    source=/work/work/normalized/shadow-4.20.4
    volume=/rustbox-shadow
    evidence=/work/work/analysis/shadow-4.20.4/normalized
    mkdir -p "$(dirname "$evidence")"
    staging=$(mktemp -d "$evidence.staging.XXXXXX")
    programs="chage chfn chgpasswd chpasswd chsh faillog getsubids gpasswd groupadd groupdel groupmod grpck grpconv grpunconv lastlog login newgidmap newgrp newuidmap newusers nologin passwd pwck pwconv pwunconv su useradd userdel usermod vipw sg vigr"

    configure_build()
    {
      compiler=$1
      build=$volume/normalized-$compiler
      rm -rf "$build"
      mkdir -p "$build"
      cd "$build"
      CC="$compiler" CFLAGS="-O2 -g -fno-omit-frame-pointer" \
      ac_cv_lib_econf_econf_readDirs=no \
        "$source/configure" \
          --disable-logind --disable-nls --enable-lastlog \
          --enable-shadowgrp --enable-subordinate-ids \
          --without-audit --without-libpam --without-btrfs \
          --without-selinux --without-acl --without-skey --without-tcb \
          --without-bcrypt --with-yescrypt --without-nscd --without-sssd \
          --with-su --without-libbsd --without-fcaps \
          --disable-shared --enable-static
      bear --output "$staging/$compiler-compile-commands.json" -- \
        make -j"$(nproc)"
    }

    program_path()
    {
      build=$1
      name=$2
      case "$name" in
        sg) name=newgrp ;;
        vigr) name=vipw ;;
      esac
      path=$build/src/$name
      payload=$build/src/.libs/$name
      if test -x "$payload"; then path=$payload; fi
      printf "%s\n" "$path"
    }

    entrypoint()
    {
      case "$1" in
        sg) name=newgrp ;;
        vigr) name=vipw ;;
        *) name=$1 ;;
      esac
      printf "rustbox_shadow_%s_main\n" "$name"
    }

    publish_programs()
    {
      compiler=$1
      build=$volume/normalized-$compiler
      output=$volume/normalized-programs-$compiler
      rm -rf "$output"
      mkdir -p "$output"
      for name in $programs; do
        path=$(program_path "$build" "$name")
        symbol=$(entrypoint "$name")
        test -x "$path"
        test "$(nm -g --defined-only "$path" | awk -v symbol="$symbol" '\''$NF == symbol { n++ } END { print n+0 }'\'')" -eq 1
        ln -s "$path" "$output/$name"
        readelf -d "$path" >"$staging/$compiler-$name.dynamic"
        nm -g --defined-only "$path" >"$staging/$compiler-$name.symbols"
      done
    }

    run_units()
    {
      compiler=$1
      build=$volume/normalized-$compiler
      set +e
      make -C "$build" check >"$staging/$compiler-test.log" 2>&1
      status=$?
      set -e
      printf "%s\n" "$status" >"$staging/$compiler-test.status"
    }

    configure_build gcc >"$staging/gcc-build.log" 2>&1
    configure_build clang-18 >"$staging/clang-build.log" 2>&1
    publish_programs gcc
    publish_programs clang-18
    run_units gcc
    run_units clang-18
    chmod -R a+rwX "$staging"
    rm -rf "$evidence"
    mv "$staging" "$evidence"
  '
