#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
"$root/scripts/normalize_gawk.sh"
RUSTBOX_TOOL_IMAGE=rustbox-gawk:2026-11-22 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    volume=/rustbox-gawk
    source=$volume/normalized-source
    oracle=/work/work/analysis/gawk-5.4.0/oracle
    output=/work/work/analysis/gawk-5.4.0/normalized
    configure_flags="--prefix=/usr --disable-dependency-tracking --enable-extensions --with-readline=/usr --with-mpfr=/usr"
    manifest_sha256=$(sha256sum /work/work/analysis/gawk-5.4.0/normalization-manifest.json | cut -d" " -f1)
    mkdir -p "$output"

    build_one()
    {
      compiler=$1
      cc=$2
      flags=$3
      linker_flags=$4
      build=$volume/normalized-$compiler
      install_root=$output/$compiler-root
      configuration="$manifest_sha256|$cc|$flags|$linker_flags|$configure_flags"
      if test ! -f "$build/.rustbox-configuration" || \
          test "$(cat "$build/.rustbox-configuration")" != "$configuration"; then
        rm -rf "$build" "$install_root"
        mkdir -p "$build" "$install_root"
        cd "$build"
        CC="$cc" CFLAGS="$flags" LDFLAGS="$linker_flags" \
          "$source/configure" $configure_flags >"$output/$compiler-configure.log" 2>&1
        grep -q "^#define DYNAMIC 1" config.h
        grep -q "^#define HAVE_LIBREADLINE 1" config.h
        grep -q "^#define HAVE_MPFR 1" config.h
        grep -q "^#define USE_PERSISTENT_MALLOC 1" config.h
        bear_mode=--force-preload
        test "$compiler" != sanitizer || bear_mode=--force-wrapper
        bear "$bear_mode" --output compile_commands.json -- \
          make -j"$(nproc)" >"$output/$compiler-build.log" 2>&1
        printf "%s\n" "$configuration" >.rustbox-configuration
        chmod -R a+rwX "$build"
      else
        cd "$build"
        rm -rf "$install_root"
        mkdir -p "$install_root"
      fi

      set +e
      if test "$compiler" = sanitizer; then
        runuser --user=nobody -- env \
          ASAN_OPTIONS=detect_leaks=0:halt_on_error=1:allocator_may_return_null=1 \
          UBSAN_OPTIONS=halt_on_error=1 \
          make -k -j"$(nproc)" check >"$output/$compiler-check.log" 2>&1
      else
        runuser --user=nobody -- make -k -j"$(nproc)" check \
          >"$output/$compiler-check.log" 2>&1
      fi
      check_status=$?
      set -e
      test "$check_status" -ne 0
      test "$(grep -c "Segmentation fault.*GAWK_PERSIST_FILE=test.pma" \
        "$output/$compiler-check.log")" -eq 1
      test "$(grep -c "Error 139" "$output/$compiler-check.log")" -eq 1
      ! grep -q "runtime error:" "$output/$compiler-check.log"
      ! grep -q "ERROR: AddressSanitizer" "$output/$compiler-check.log"
      ! grep -q " differ:" "$output/$compiler-check.log"
      if grep -E "make(\[[0-9]+\])?: \\*\\*\\*" "$output/$compiler-check.log" \
           | grep -Ev "\[[^]]*: (pma|pma-tests|check-recursive|check)\] Error" \
           | grep -q .; then
        exit 1
      fi
      make install DESTDIR="$install_root" >"$output/$compiler-install.log" 2>&1
      cp compile_commands.json "$output/$compiler-compile-commands.json"
      find "$install_root/usr" \( -type f -o -type l \) | sort \
        >"$output/$compiler-installed-files.txt"
    }

    build_one gcc gcc "-O2 -g -fno-omit-frame-pointer" ""
    build_one clang clang-18 "-O2 -g -fno-omit-frame-pointer" ""
    build_one sanitizer gcc \
      "-O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer" \
      "-fsanitize=address,undefined"

    for compiler in gcc clang; do
      python3 /work/tests/gawk-oracle-differential.py \
        --gcc-build "$volume/oracle-$compiler" \
        --clang-build "$volume/normalized-$compiler" \
        --output "$output/$compiler-differential.json"
    done

    for option in --version --help; do
      label=$(printf "%s" "$option" | tr -d -)
      valgrind --leak-check=full --show-leak-kinds=all \
        --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
        --log-file="$output/valgrind-$label.log" \
        "$volume/normalized-gcc/gawk" "$option" \
        >"$output/valgrind-$label.out" 2>&1
      grep -q "ERROR SUMMARY: 0 errors" "$output/valgrind-$label.log"
      grep -q "definitely lost: 0 bytes" "$output/valgrind-$label.log"
      grep -q "indirectly lost: 0 bytes" "$output/valgrind-$label.log"
      grep -q "possibly lost: 0 bytes" "$output/valgrind-$label.log"
    done
  '
