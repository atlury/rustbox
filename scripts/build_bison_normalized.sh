#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-bison:2026-11-23 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    release=/work/work/normalized/bison-3.8.2
    volume=/rustbox-bison
    source=$volume/normalized-source
    build=$volume/normalized-clang
    output=/work/work/analysis/bison-3.8.2/normalized
    install_root=$output/clang-root
    mkdir -p "$source" "$build" "$output" "$install_root"
    if test ! -f "$source/configure"; then
      cp -a "$release/." "$source/"
    fi
    cd "$build"
    if test ! -f Makefile; then
      CC=clang-18 CXX=clang++-18 \
        CFLAGS="-O2 -g -fno-omit-frame-pointer" \
        CXXFLAGS="-O2 -g -fno-omit-frame-pointer" \
        JAVA=no JAVAC=no DC= \
        "$source/configure" --prefix=/usr --disable-dependency-tracking \
        >"$output/clang-configure.log" 2>&1
    fi
    if test ! -f .rustbox-normalized-build-complete; then
      bear --force-preload --output compile_commands.json -- \
        make -j"$(nproc)" AUTOCONF=true AUTOHEADER=true \
          AUTOMAKE=true ACLOCAL=true >"$output/clang-build.log" 2>&1
      touch .rustbox-normalized-build-complete
    fi
    if test ! -f .rustbox-normalized-check-complete; then
      make -j"$(nproc)" check AUTOCONF=true AUTOHEADER=true \
        AUTOMAKE=true ACLOCAL=true >"$output/clang-check.log" 2>&1
      touch .rustbox-normalized-check-complete
    fi
    make install DESTDIR="$install_root" \
      >"$output/clang-install.log" 2>&1
    cp compile_commands.json "$output/clang-compile-commands.json"
    find "$install_root/usr" \( -type f -o -type l \) | sort \
      >"$output/clang-installed-files.txt"
    chmod -R a+rwX "$source" "$build" "$install_root"

    python3 -B /work/tests/bison-oracle-differential.py \
      --gcc /work/work/analysis/bison-3.8.2/oracle/gcc-root/usr/bin/bison \
      --gcc-datadir /work/work/analysis/bison-3.8.2/oracle/gcc-root/usr/share/bison \
      --clang "$install_root/usr/bin/bison" \
      --clang-datadir "$install_root/usr/share/bison" \
      --source /work/work/upstream/bison-3.8.2 \
      --output "$output/canonical-differential.json"

    for option in --version --help; do
      label=$(printf "%s" "$option" | tr -d -)
      valgrind --leak-check=full --show-leak-kinds=all \
        --log-file="$output/valgrind-$label.log" \
        "$install_root/usr/bin/bison" "$option" \
        >"$output/valgrind-$label.out" 2>&1
    done
  '
