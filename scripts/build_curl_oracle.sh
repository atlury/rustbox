#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-curl:2026-11-23 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    export PYTHONDONTWRITEBYTECODE=1
    source=/work/work/upstream/curl-8.23.0
    volume=/rustbox-curl
    output=/work/work/analysis/curl-8.23.0/oracle
    gcc_build=$volume/oracle-gcc
    clang_build=$volume/oracle-clang

    configure_build()
    {
      build=$1
      compiler=$2
      mkdir -p "$build"
      cd "$build"
      CC="$compiler" CFLAGS="-O2 -g -fno-omit-frame-pointer" \
        "$source/configure" \
          --disable-dependency-tracking --disable-shared --enable-static \
          --without-ssl --without-zlib --without-brotli --without-zstd \
          --without-libpsl --without-libgsasl --without-libssh2 --without-libssh \
          --without-libidn2 --without-nghttp2 --without-ngtcp2 --without-nghttp3 \
          --without-quiche --without-libuv --without-gssapi \
          --disable-ldap --disable-ldaps \
          --without-ca-bundle --without-ca-path --without-ca-fallback \
          --without-ca-embed
      bear --output compile_commands.json -- make -j"$(nproc)"
    }

    run_suite()
    {
      build=$1
      log=$2
      chown -R nobody:nogroup "$build"
      cd "$build"
      runuser --user=nobody -- make test TFLAGS="-n -j$(nproc)" >"$log" 2>&1
    }

    rm -rf "$output" "$gcc_build" "$clang_build"
    mkdir -p "$output"

    configure_build "$gcc_build" gcc >"$output/gcc-build.log" 2>&1
    run_suite "$gcc_build" "$output/gcc-test.log"

    configure_build "$clang_build" clang-18 >"$output/clang-build.log" 2>&1
    run_suite "$clang_build" "$output/clang-test.log"

    for compiler in gcc clang; do
      case $compiler in
        gcc) build=$gcc_build ;;
        clang) build=$clang_build ;;
      esac
      cp "$build/compile_commands.json" "$output/$compiler-compile-commands.json"
      cp "$build/lib/curl_config.h" "$output/config-$compiler.h"
      cp "$build/src/tool_ca_embed.c" "$output/tool_ca_embed-$compiler.c"
      cp "$build/src/tool_hugehelp.c" "$output/tool_hugehelp-$compiler.c"
      cp "$build/src/curl" "$output/curl-$compiler"
      cp "$build/curl-config" "$output/curl-config-$compiler"
      cp "$build/lib/.libs/libcurl.a" "$output/libcurl-$compiler.a"
      readelf -d "$output/curl-$compiler" >"$output/curl-$compiler.dynamic"
      "$output/curl-$compiler" --version >"$output/version-$compiler.txt"
      {
        "$output/curl-config-$compiler" --version
        "$output/curl-config-$compiler" --features
        "$output/curl-config-$compiler" --protocols
        "$output/curl-config-$compiler" --static-libs
      } >"$output/curl-config-$compiler.txt"
      "$output/curl-config-$compiler" --configure \
        >"$output/curl-config-$compiler.configure.txt"
    done
    cmp "$output/version-gcc.txt" "$output/version-clang.txt"
    cmp "$output/curl-config-gcc.txt" "$output/curl-config-clang.txt"
    cmp "$output/tool_ca_embed-gcc.c" "$output/tool_ca_embed-clang.c"
    cmp "$output/tool_hugehelp-gcc.c" "$output/tool_hugehelp-clang.c"
    python3 /work/tests/curl-oracle-differential.py \
      --gcc "$output/curl-gcc" --clang "$output/curl-clang" \
      --output "$output/differential.json"

    valgrind --leak-check=full --show-leak-kinds=all \
      --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
      --log-file="$output/valgrind-version.log" \
      "$output/curl-gcc" --version >"$output/valgrind-version.out"
    printf "rustbox-curl-file-payload\n" >"$output/file-input"
    valgrind --leak-check=full --show-leak-kinds=all \
      --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
      --log-file="$output/valgrind-file.log" \
      "$output/curl-gcc" --silent --show-error \
        "file://$output/file-input" >"$output/valgrind-file.out"
    cmp "$output/file-input" "$output/valgrind-file.out"
  '
