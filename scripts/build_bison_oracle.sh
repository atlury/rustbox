#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-bison:2026-11-23 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    release=/work/work/upstream/bison-3.8.2
    volume=/rustbox-bison
    source=$volume/source-pristine
    output=/work/work/analysis/bison-3.8.2/oracle
    configure_flags="--prefix=/usr --disable-dependency-tracking"
    mkdir -p "$source" "$output"
    if test ! -f "$source/configure"; then
      cp -a "$release/." "$source/"
    fi

    build_one()
    {
      compiler=$1
      cc=$2
      cxx=$3
      flags=$4
      linker_flags=$5
      build=$volume/oracle-v3-$compiler
      install_root=$output/$compiler-root
      mkdir -p "$build" "$install_root"
      cd "$build"
      if test ! -f Makefile; then
        CC="$cc" CXX="$cxx" CFLAGS="$flags" CXXFLAGS="$flags" \
          LDFLAGS="$linker_flags" JAVA=no JAVAC=no DC= \
          "$source/configure" $configure_flags \
          >"$output/$compiler-configure.log" 2>&1
      fi
      if test ! -f .rustbox-oracle-build-complete; then
        bear_mode=--force-preload
        test "$compiler" != sanitizer || bear_mode=--force-wrapper
        bear "$bear_mode" --output compile_commands.json -- \
          make -j"$(nproc)" AUTOCONF=true AUTOHEADER=true \
            AUTOMAKE=true ACLOCAL=true >"$output/$compiler-build.log" 2>&1
        touch .rustbox-oracle-build-complete
      fi
      if test ! -f .rustbox-oracle-check-complete; then
        if test "$compiler" = sanitizer; then
          ASAN_OPTIONS=detect_leaks=0:halt_on_error=1 \
          UBSAN_OPTIONS=halt_on_error=1 \
            make -j"$(nproc)" check AUTOCONF=true AUTOHEADER=true \
              AUTOMAKE=true ACLOCAL=true >"$output/$compiler-check.log" 2>&1
        else
          make -j"$(nproc)" check AUTOCONF=true AUTOHEADER=true \
            AUTOMAKE=true ACLOCAL=true >"$output/$compiler-check.log" 2>&1
        fi
        touch .rustbox-oracle-check-complete
      fi
      make install DESTDIR="$install_root" \
        >"$output/$compiler-install.log" 2>&1
      cp compile_commands.json "$output/$compiler-compile-commands.json"
      find "$install_root/usr" \( -type f -o -type l \) | sort \
        >"$output/$compiler-installed-files.txt"
      chmod -R a+rwX "$build" "$install_root"
    }

    build_one gcc gcc g++ "-O2 -g -fno-omit-frame-pointer" ""
    build_one clang clang-18 clang++-18 \
      "-O2 -g -fno-omit-frame-pointer" ""
    build_one sanitizer gcc g++ \
      "-O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer" \
      "-fsanitize=address,undefined"

    for option in --version --help; do
      label=$(printf "%s" "$option" | tr -d -)
      valgrind --leak-check=full --show-leak-kinds=all \
        --log-file="$output/valgrind-$label.log" \
        "$volume/oracle-v3-gcc/src/bison" "$option" \
        >"$output/valgrind-$label.out" 2>&1
    done
  '
