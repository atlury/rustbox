#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
"$root/scripts/normalize_acl.sh"
RUSTBOX_TOOL_IMAGE=rustbox-acl:2026-11-21 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    volume=/rustbox-acl
    source=$volume/normalized-source
    output=/work/work/analysis/acl-2.4.0/normalized
    oracle=/work/work/analysis/acl-2.4.0/oracle
    gcc_build=$volume/normalized-gcc
    clang_build=$volume/normalized-clang
    sanitizer_build=$volume/normalized-sanitizer
    ordinary_tests="test/cp.run test/getfacl-lfs.run test/getfacl-noacl.run test/getfacl-recursive.run test/malformed-restore.run test/misc.run test/setfacl-X.run test/root/getfacl.run test/root/restore.run test/root/setfacl.run test/nfs/nfsacl.run test/nfs/nfs-dir.run test/restore.run test/sbits-restore.run test/utf8-filenames.run"

    run_logged()
    {
      log=$1
      shift
      if "$@" >"$log" 2>&1; then cat "$log"; else status=$?; cat "$log"; return "$status"; fi
    }

    run_platform_check()
    {
      compiler=$1
      if make check TESTS="test/root/permissions.run" \
          >"$output/$compiler-platform-permissions.log" 2>&1; then
        cat "$output/$compiler-platform-permissions.log"
        echo "normalized ACL container permission test unexpectedly passed" >&2
        return 1
      fi
      cat "$output/$compiler-platform-permissions.log"
      grep -q "# TOTAL: 1" "$output/$compiler-platform-permissions.log"
      grep -q "# FAIL:  1" "$output/$compiler-platform-permissions.log"
    }

    rm -rf "$gcc_build" "$clang_build" "$sanitizer_build"
    mkdir -p "$gcc_build" "$clang_build" "$sanitizer_build" "$output"

    build_one()
    {
      compiler=$1
      cc=$2
      build=$3
      cd "$build"
      CC="$cc" CFLAGS="-O2 -g -fno-omit-frame-pointer" \
        "$source/configure" --disable-dependency-tracking --disable-nls \
          --enable-shared --enable-static
      bear --output compile_commands.json -- make -j"$(nproc)"
      run_platform_check "$compiler"
      run_logged "$output/$compiler-check.log" \
        make -j"$(nproc)" check TESTS="$ordinary_tests"
      cp compile_commands.json "$output/$compiler-compile-commands.json"
      for utility in chacl getfacl setfacl; do
        cp "tools/$utility.o" "$output/$utility-$compiler.o"
      done
      rm chacl getfacl setfacl .libs/chacl .libs/getfacl .libs/setfacl
      make LDFLAGS=-static chacl getfacl setfacl
      for utility in chacl getfacl setfacl; do
        cp "$utility" "$output/$utility-$compiler"
      done
    }

    build_one gcc gcc "$gcc_build"
    build_one clang clang-18 "$clang_build"

    cd "$sanitizer_build"
    CC=gcc CFLAGS="-O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer" \
      LDFLAGS="-fsanitize=address,undefined" \
      "$source/configure" --disable-dependency-tracking --disable-nls \
        --enable-shared --enable-static
    bear --force-wrapper --output compile_commands.json -- make -j"$(nproc)"
    # The root fixture uses tracing around su; LeakSanitizer cannot run under
    # ptrace.  Valgrind below remains the independent leak gate.
    ASAN_OPTIONS=verify_asan_link_order=0:detect_leaks=0:halt_on_error=1 \
      UBSAN_OPTIONS=halt_on_error=1 run_platform_check sanitizer
    ASAN_OPTIONS=verify_asan_link_order=0:detect_leaks=0:halt_on_error=1 \
      UBSAN_OPTIONS=halt_on_error=1 \
      run_logged "$output/sanitizer-check.log" \
        make -j"$(nproc)" check TESTS="$ordinary_tests"
    cp compile_commands.json "$output/sanitizer-compile-commands.json"

    python3 /work/tests/acl-oracle-differential.py \
      --gcc-directory "$oracle" --gcc-suffix gcc \
      --clang-directory "$output" --clang-suffix gcc \
      --output "$output/canonical-normalized-gcc-differential.json"
    python3 /work/tests/acl-oracle-differential.py \
      --gcc-directory "$oracle" --gcc-suffix clang \
      --clang-directory "$output" --clang-suffix clang \
      --output "$output/canonical-normalized-clang-differential.json"

    cd "$volume"
    printf "payload\n" > normalized-valgrind-target
    valgrind --leak-check=full --show-leak-kinds=all \
      --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
      --log-file="$output/valgrind-setfacl.log" \
      "$output/setfacl-gcc" -m u:12345:rw- normalized-valgrind-target
    valgrind --leak-check=full --show-leak-kinds=all \
      --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
      --log-file="$output/valgrind-getfacl.log" \
      "$output/getfacl-gcc" -n normalized-valgrind-target \
      > "$output/valgrind-getfacl.out"
    for utility in setfacl getfacl; do
      grep -q "ERROR SUMMARY: 0 errors" "$output/valgrind-$utility.log"
      grep -q "All heap blocks were freed -- no leaks are possible" \
        "$output/valgrind-$utility.log"
    done
  '
