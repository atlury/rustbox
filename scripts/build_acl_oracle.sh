#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-acl:2026-11-21 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    release=/work/work/upstream/acl-2.4.0
    volume=/rustbox-acl
    source=$volume/source
    gcc_build=$volume/canonical-gcc
    clang_build=$volume/canonical-clang
    sanitizer_build=$volume/canonical-sanitizer
    evidence=/work/work/analysis/acl-2.4.0/oracle

    run_logged()
    {
      log=$1
      shift
      if "$@" >"$log" 2>&1; then cat "$log"; else status=$?; cat "$log"; return "$status"; fi
    }

    ordinary_tests="test/cp.run test/getfacl-lfs.run test/getfacl-noacl.run test/getfacl-recursive.run test/malformed-restore.run test/misc.run test/setfacl-X.run test/root/getfacl.run test/root/restore.run test/root/setfacl.run test/nfs/nfsacl.run test/nfs/nfs-dir.run test/restore.run test/sbits-restore.run test/utf8-filenames.run"

    run_platform_check()
    {
      compiler=$1
      if make check TESTS="test/root/permissions.run" \
          >"$evidence/$compiler-platform-permissions.log" 2>&1; then
        cat "$evidence/$compiler-platform-permissions.log"
        echo "ACL container permission test unexpectedly passed" >&2
        return 1
      fi
      cat "$evidence/$compiler-platform-permissions.log"
      grep -q "# TOTAL: 1" "$evidence/$compiler-platform-permissions.log"
      grep -q "# FAIL:  1" "$evidence/$compiler-platform-permissions.log"
    }

    rm -rf "$source" "$gcc_build" "$clang_build" "$sanitizer_build" "$evidence"
    mkdir -p "$source" "$evidence"
    cp -a "$release/." "$source/"

    build_one()
    {
      compiler=$1
      cc=$2
      build=$3
      mkdir "$build"
      cd "$build"
      CC="$cc" CFLAGS="-O2 -g -fno-omit-frame-pointer" \
        "$source/configure" --disable-dependency-tracking --disable-nls \
          --enable-shared --enable-static
      bear --output compile_commands.json -- make -j"$(nproc)"
      run_platform_check "$compiler"
      run_logged "$evidence/$compiler-check.log" \
        make -j"$(nproc)" check TESTS="$ordinary_tests"
      cp compile_commands.json "$evidence/$compiler-compile-commands.json"
      # The normal shared build is required by the upstream LD_PRELOAD identity
      # fixture.  Relink only the three finished oracles statically afterwards,
      # so evidence never depends on a libtool wrapper or the host libacl.
      # Libtool -static embeds its own libraries while keeping glibc dynamic.
      rm chacl getfacl setfacl .libs/chacl .libs/getfacl .libs/setfacl
      make LDFLAGS=-static chacl getfacl setfacl
      for utility in chacl getfacl setfacl; do
        cp "$utility" "$evidence/$utility-$compiler"
      done
    }

    build_one gcc gcc "$gcc_build"
    build_one clang clang-18 "$clang_build"

    mkdir "$sanitizer_build"
    cd "$sanitizer_build"
    CC=gcc CFLAGS="-O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer" \
      LDFLAGS="-fsanitize=address,undefined" \
      "$source/configure" --disable-dependency-tracking --disable-nls \
        --enable-shared --enable-static
    bear --force-wrapper --output compile_commands.json -- make -j"$(nproc)"
    # The tests intentionally preload libtestlookup before launching tools.
    # Permit that upstream fixture while retaining all actual ASan/UBSan checks.
    ASAN_OPTIONS=verify_asan_link_order=0:detect_leaks=1:halt_on_error=1 \
      UBSAN_OPTIONS=halt_on_error=1 \
      run_platform_check sanitizer
    if ASAN_OPTIONS=verify_asan_link_order=0:detect_leaks=1:halt_on_error=1 \
        UBSAN_OPTIONS=halt_on_error=1 \
        run_logged "$evidence/sanitizer-check.log" \
          make -j"$(nproc)" check TESTS="$ordinary_tests"
    then
      echo "ACL canonical sanitizer baseline unexpectedly passed" >&2
      exit 1
    fi
    grep -q "# TOTAL: 15" "$evidence/sanitizer-check.log"
    grep -q "# PASS:  12" "$evidence/sanitizer-check.log"
    grep -q "# XFAIL: 2" "$evidence/sanitizer-check.log"
    grep -q "# FAIL:  1" "$evidence/sanitizer-check.log"
    cp test/root/setfacl.log "$evidence/sanitizer-setfacl-ub.log"
    test "$(grep -c "runtime error: applying non-zero offset .* to null pointer" \
      "$evidence/sanitizer-setfacl-ub.log")" -eq 4
    cp compile_commands.json "$evidence/sanitizer-compile-commands.json"

    python3 /work/tests/acl-oracle-differential.py \
      --gcc-directory "$evidence" --clang-directory "$evidence" \
      --output "$evidence/differential.json"

    cd "$volume"
    rm -f valgrind-target
    printf "payload\n" > valgrind-target
    valgrind --leak-check=full --show-leak-kinds=all \
      --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
      --log-file="$evidence/valgrind-setfacl.log" \
      "$evidence/setfacl-gcc" -m u:12345:rw- valgrind-target
    valgrind --leak-check=full --show-leak-kinds=all \
      --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
      --log-file="$evidence/valgrind-getfacl.log" \
      "$evidence/getfacl-gcc" -n valgrind-target \
      > "$evidence/valgrind-getfacl.out"
    for utility in setfacl getfacl; do
      grep -q "ERROR SUMMARY: 0 errors" "$evidence/valgrind-$utility.log"
      grep -q "All heap blocks were freed -- no leaks are possible" \
        "$evidence/valgrind-$utility.log"
    done
  '
