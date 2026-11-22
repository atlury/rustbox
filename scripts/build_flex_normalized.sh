#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-flex:2026-11-22 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    release=/work/work/normalized/flex-2.6.4
    volume=/rustbox-flex
    source=$volume/normalized-source
    oracle=$volume/oracle-gcc/src/flex
    output=/work/work/analysis/flex-2.6.4/normalized
    manifest=/work/work/analysis/flex-2.6.4/normalization-manifest.json
    test -x "$oracle"
    test -s "$manifest"
    mkdir -p "$source" "$output"
    if test ! -f "$source/configure"; then
      cp -a "$release/." "$source/"
    fi

    build_one()
    {
      compiler=$1
      cc=$2
      cxx=$3
      build=$volume/normalized-$compiler
      install_root=$output/$compiler-root
      mkdir -p "$build" "$install_root"
      cd "$build"
      if test ! -f Makefile; then
        CC="$cc" CXX="$cxx" \
          CFLAGS="-O2 -g -fno-omit-frame-pointer" \
          CXXFLAGS="-O2 -g -fno-omit-frame-pointer" \
          "$source/configure" --prefix=/usr --disable-dependency-tracking \
          >"$output/$compiler-configure.log" 2>&1
      fi
      if test ! -f .rustbox-normalized-build-complete; then
        bear --force-preload --output compile_commands.json -- \
          make -j"$(nproc)" >"$output/$compiler-build.log" 2>&1
        touch .rustbox-normalized-build-complete
      fi
      if test ! -f .rustbox-normalized-check-complete; then
        make -j"$(nproc)" check >"$output/$compiler-check.log" 2>&1
        touch .rustbox-normalized-check-complete
      fi
      make install DESTDIR="$install_root" \
        >"$output/$compiler-install.log" 2>&1
      cp compile_commands.json "$output/$compiler-compile-commands.json"
      find "$install_root/usr" \( -type f -o -type l \) | sort \
        >"$output/$compiler-installed-files.txt"
      chmod -R a+rwX "$build" "$install_root"
    }

    build_one gcc gcc g++
    build_one clang clang-18 clang++-18

    python3 /work/tests/flex-oracle-differential.py \
      --gcc "$oracle" \
      --clang "$volume/normalized-gcc/src/flex" \
      --source "$source" \
      --output "$output/canonical-differential.json"

    for record in "help --help 0" "version --version 0" \
                  "invalid --definitely-invalid 1"; do
      set -- $record
      label=$1
      option=$2
      expected=$3
      set +e
      valgrind --leak-check=full --show-leak-kinds=all \
        --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
        --log-file="$output/valgrind-$label.log" \
        "$volume/normalized-gcc/src/flex" "$option" \
        >"$output/valgrind-$label.out" 2>&1
      status=$?
      set -e
      test "$status" -eq "$expected"
      grep -q "ERROR SUMMARY: 0 errors" "$output/valgrind-$label.log"
      grep -Eq "All heap blocks were freed|definitely lost: 0 bytes" \
        "$output/valgrind-$label.log"
      grep -Eq "All heap blocks were freed|indirectly lost: 0 bytes" \
        "$output/valgrind-$label.log"
      grep -Eq "All heap blocks were freed|possibly lost: 0 bytes" \
        "$output/valgrind-$label.log"
    done
  '
