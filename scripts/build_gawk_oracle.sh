#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-gawk:2026-11-22 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    release=/work/work/upstream/gawk-5.4.0
    volume=/rustbox-gawk
    source=$volume/source
    output=/work/work/analysis/gawk-5.4.0/oracle
    configure_flags="--prefix=/usr --disable-dependency-tracking --enable-extensions --with-readline=/usr --with-mpfr=/usr"
    mkdir -p "$source" "$output"
    if test ! -f "$source/configure"; then
      cp -a "$release/." "$source/"
    fi

    build_one()
    {
      compiler=$1
      cc=$2
      flags=$3
      linker_flags=$4
      build=$volume/oracle-$compiler
      install_root=$output/$compiler-root
      if test ! -x "$build/gawk"; then
        mkdir -p "$build" "$install_root"
        cd "$build"
        CC="$cc" CFLAGS="$flags" LDFLAGS="$linker_flags" \
          "$source/configure" $configure_flags \
          >"$output/$compiler-configure.log" 2>&1
        grep -q "^#define DYNAMIC 1" config.h
        grep -q "^#define HAVE_LIBREADLINE 1" config.h
        grep -q "^#define HAVE_MPFR 1" config.h
        grep -q "^#define USE_PERSISTENT_MALLOC 1" config.h
        bear_mode=--force-preload
        test "$compiler" != sanitizer || bear_mode=--force-wrapper
        bear "$bear_mode" --output compile_commands.json -- \
          make -j"$(nproc)" >"$output/$compiler-build.log" 2>&1
        chmod -R a+rwX "$build"
      else
        cd "$build"
      fi
      if test ! -f .rustbox-oracle-check-complete; then
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
        # PMA maps a persistent heap at an identical virtual address across
        # executions.  Docker amd64 emulation on this ARM host cannot honor
        # the second mapping and the canonical binary dies in the PMA-only
        # test.  Keep PMA compiled in, record the defect, and reject every
        # other failing target.
        if test "$check_status" -ne 0; then
          test "$(grep -c "Segmentation fault.*GAWK_PERSIST_FILE=test.pma" \
            "$output/$compiler-check.log")" -eq 1
          test "$(grep -c "Error 139" "$output/$compiler-check.log")" -eq 1
          if grep -E "make(\[[0-9]+\])?: \\*\\*\\*" \
               "$output/$compiler-check.log" \
             | grep -Ev "\[[^]]*: (pma|pma-tests|check-recursive|check)\] Error" \
             | grep -q .; then
            exit 1
          fi
        fi
        touch .rustbox-oracle-check-complete
      fi
      make install DESTDIR="$install_root" \
        >"$output/$compiler-install.log" 2>&1
      cp compile_commands.json "$output/$compiler-compile-commands.json"
      find "$install_root/usr" \( -type f -o -type l \) | sort \
        >"$output/$compiler-installed-files.txt"
    }

    build_one gcc gcc "-O2 -g -fno-omit-frame-pointer" ""
    build_one clang clang-18 "-O2 -g -fno-omit-frame-pointer" ""
    build_one sanitizer gcc \
      "-O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer" \
      "-fsanitize=address,undefined"

    python3 /work/tests/gawk-oracle-differential.py \
      --gcc-build "$volume/oracle-gcc" \
      --clang-build "$volume/oracle-clang" \
      --output "$output/differential.json"

    for option in --version --help; do
      label=$(printf "%s" "$option" | tr -d -)
      valgrind --leak-check=full --show-leak-kinds=all \
        --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
        --log-file="$output/valgrind-$label.log" \
        "$volume/oracle-gcc/gawk" "$option" \
        >"$output/valgrind-$label.out" 2>&1
      grep -q "ERROR SUMMARY: 0 errors" "$output/valgrind-$label.log"
      grep -Eq "All heap blocks were freed|definitely lost: 0 bytes" \
        "$output/valgrind-$label.log"
      grep -Eq "All heap blocks were freed|indirectly lost: 0 bytes" \
        "$output/valgrind-$label.log"
      grep -Eq "All heap blocks were freed|possibly lost: 0 bytes" \
        "$output/valgrind-$label.log"
    done
  '
