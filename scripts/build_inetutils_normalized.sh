#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
"$root/scripts/normalize_inetutils.sh"
RUSTBOX_TOOL_IMAGE=rustbox-inetutils:2026-11-23 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    release=/work/work/normalized/inetutils-2.8
    volume=/rustbox-inetutils
    source=$volume/normalized-source
    output=/work/work/analysis/inetutils-2.8/normalized
    configure_flags="--disable-dependency-tracking --disable-systemd --without-pam --without-wrap --without-krb4 --without-krb5 --without-shishi --without-idn"
    rm -rf "$source" "$volume/normalized-gcc" "$volume/normalized-clang" "$output"
    mkdir -p "$source" "$output"
    cp -a "$release/." "$source/"

    build_one()
    {
      compiler=$1
      cc=$2
      build=$volume/normalized-$compiler
      mkdir -p "$build"
      cd "$build"
      CC="$cc" CFLAGS="-O2 -g -fno-omit-frame-pointer" \
        "$source/configure" $configure_flags \
        >"$output/$compiler-build.log" 2>&1
      bear --output compile_commands.json -- make -j"$(nproc)" \
        >>"$output/$compiler-build.log" 2>&1
      cp compile_commands.json "$output/$compiler-compile-commands.json"
      set +e
      make -j"$(nproc)" check >"$output/$compiler-test.log" 2>&1
      status=$?
      set -e
      printf "%s\n" "$status" >"$output/$compiler-test.status"
      cp tests/test-suite.log "$output/$compiler-test-suite.log"
    }

    build_one gcc gcc
    build_one clang clang-18

    python3 /work/tests/inetutils-oracle-differential.py \
      --gcc-root "$volume/oracle-gcc" --clang-root "$volume/normalized-gcc" \
      --output "$output/gcc-differential.json"
    python3 /work/tests/inetutils-oracle-differential.py \
      --gcc-root "$volume/oracle-clang" --clang-root "$volume/normalized-clang" \
      --output "$output/clang-differential.json"

    for item in \
      hostname:src/hostname \
      dnsdomainname:src/dnsdomainname \
      ifconfig:ifconfig/ifconfig \
      whois:whois/whois
    do
      name=${item%%:*}
      relative=${item#*:}
      valgrind --leak-check=full --show-leak-kinds=all \
        --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
        --log-file="$output/valgrind-$name.log" \
        "$volume/normalized-gcc/$relative" --version \
        >"$output/valgrind-$name.out"
      grep -q "ERROR SUMMARY: 0 errors" "$output/valgrind-$name.log"
      test "$(nm -g --defined-only "$volume/normalized-gcc/$relative" | \
        grep -c " rustbox_inetutils_${name}_main$")" -eq 1
    done
    chmod -R a+rwX "$source" "$volume/normalized-gcc" \
      "$volume/normalized-clang" "$output"
  '
