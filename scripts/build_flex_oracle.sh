#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-flex:2026-11-22 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    release=/work/work/upstream/flex-2.6.4
    volume=/rustbox-flex
    source=$volume/source
    output=/work/work/analysis/flex-2.6.4/oracle
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
      build=$volume/oracle-$compiler
      install_root=$output/$compiler-root
      mkdir -p "$build" "$install_root"
      cd "$build"
      if test ! -f Makefile; then
        if test "$compiler" = sanitizer; then
          # ASan intentionally changes malloc(0)/realloc(0) observations.
          # Keep the production glibc configuration proven by both ordinary
          # compiler builds instead of enabling the unused Flex replacement.
          ac_cv_func_malloc_0_nonnull=yes \
          ac_cv_func_realloc_0_nonnull=yes \
          CC="$cc" CXX="$cxx" CFLAGS="$flags" CXXFLAGS="$flags" \
            LDFLAGS="$linker_flags" "$source/configure" $configure_flags \
            >"$output/$compiler-configure.log" 2>&1
        else
          CC="$cc" CXX="$cxx" CFLAGS="$flags" CXXFLAGS="$flags" \
            LDFLAGS="$linker_flags" "$source/configure" $configure_flags \
            >"$output/$compiler-configure.log" 2>&1
        fi
      fi
      if test ! -f .rustbox-oracle-build-complete; then
        bear_mode=--force-preload
        test "$compiler" != sanitizer || bear_mode=--force-wrapper
        if test "$compiler" = sanitizer; then
          ASAN_OPTIONS=detect_leaks=0:halt_on_error=1:allocator_may_return_null=1 \
          UBSAN_OPTIONS=halt_on_error=1 \
            bear "$bear_mode" --output compile_commands.json -- \
              make -j"$(nproc)" >"$output/$compiler-build.log" 2>&1
        else
          bear "$bear_mode" --output compile_commands.json -- \
            make -j"$(nproc)" >"$output/$compiler-build.log" 2>&1
        fi
        touch .rustbox-oracle-build-complete
      fi
      if test ! -f .rustbox-oracle-check-complete; then
        if test "$compiler" = sanitizer; then
          ASAN_OPTIONS=detect_leaks=0:halt_on_error=1:allocator_may_return_null=1 \
          UBSAN_OPTIONS=halt_on_error=1 \
            make -j"$(nproc)" check >"$output/$compiler-check.log" 2>&1
        else
          make -j"$(nproc)" check >"$output/$compiler-check.log" 2>&1
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

    python3 /work/tests/flex-oracle-differential.py \
      --gcc "$volume/oracle-gcc/src/flex" \
      --clang "$volume/oracle-clang/src/flex" \
      --source "$source" \
      --output "$output/differential.json"

    for option in --version --help; do
      label=$(printf "%s" "$option" | tr -d -)
      valgrind --leak-check=full --show-leak-kinds=all \
        --log-file="$output/valgrind-$label.log" \
        "$volume/oracle-gcc/src/flex" "$option" \
        >"$output/valgrind-$label.out" 2>&1
      grep -q "definitely lost: 48 bytes in 1 blocks" \
        "$output/valgrind-$label.log"
      grep -q "indirectly lost: 1,368 bytes in 1 blocks" \
        "$output/valgrind-$label.log"
      grep -q "possibly lost: 0 bytes in 0 blocks" \
        "$output/valgrind-$label.log"
    done
  '
