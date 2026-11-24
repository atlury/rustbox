#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-shadow:2026-11-24 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    source=/work/work/upstream/shadow-4.20.4
    volume=/rustbox-shadow
    evidence=/work/work/analysis/shadow-4.20.4/oracle
    programs="chage chfn chgpasswd chpasswd chsh faillog getsubids gpasswd groupadd groupdel groupmod grpck grpconv grpunconv lastlog login newgidmap newgrp newuidmap newusers nologin passwd pwck pwconv pwunconv su useradd userdel usermod vipw sg vigr"

    configure_build()
    {
      compiler=$1
      build=$volume/oracle-$compiler
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
      bear --output "$evidence/$compiler-compile-commands.json" -- \
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
      if test -x "$payload"; then
        path=$payload
      fi
      printf "%s\n" "$path"
    }

    publish_programs()
    {
      compiler=$1
      build=$volume/oracle-$compiler
      output=$volume/programs-$compiler
      rm -rf "$output"
      mkdir -p "$output"
      for name in $programs; do
        path=$(program_path "$build" "$name")
        test -x "$path"
        ln -s "$path" "$output/$name"
        readelf -d "$path" >"$evidence/$compiler-$name.dynamic"
      done
    }

    run_units()
    {
      compiler=$1
      build=$volume/oracle-$compiler
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
    run_units gcc
    run_units clang-18
    chmod -R a+rwX "$evidence"
  '
