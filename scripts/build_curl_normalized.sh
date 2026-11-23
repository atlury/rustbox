#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-curl:2026-11-23 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    export PYTHONDONTWRITEBYTECODE=1
    release=/work/work/normalized/curl-8.23.0
    volume=/rustbox-curl
    source=$volume/normalized-source
    build=$volume/normalized-clang
    output=/work/work/analysis/curl-8.23.0/normalized
    oracle=/work/work/analysis/curl-8.23.0/oracle

    rm -rf "$source" "$build" "$output"
    mkdir -p "$source" "$build" "$output"
    cp -a "$release/." "$source/"

    cd "$build"
    CC=clang-18 CFLAGS="-O2 -g -fno-omit-frame-pointer" \
      "$source/configure" \
        --disable-dependency-tracking --disable-shared --enable-static \
        --without-ssl --without-zlib --without-brotli --without-zstd \
        --without-libpsl --without-libgsasl --without-libssh2 --without-libssh \
        --without-libidn2 --without-nghttp2 --without-ngtcp2 --without-nghttp3 \
        --without-quiche --without-libuv --without-gssapi \
        --disable-ldap --disable-ldaps \
        --without-ca-bundle --without-ca-path --without-ca-fallback \
        --without-ca-embed >"$output/clang-build.log" 2>&1
    bear --output compile_commands.json -- make -j"$(nproc)" \
      >>"$output/clang-build.log" 2>&1

    chown -R nobody:nogroup "$build"
    runuser --user=nobody -- make test TFLAGS="-n -j$(nproc)" \
      >"$output/clang-test.log" 2>&1
    cp compile_commands.json "$output/clang-compile-commands.json"
    cp lib/curl_config.h "$output/config-clang.h"
    cp src/tool_ca_embed.c "$output/tool_ca_embed-clang.c"
    cp src/tool_hugehelp.c "$output/tool_hugehelp-clang.c"
    cp src/curl "$output/curl-clang"
    cp curl-config "$output/curl-config-clang"
    cp lib/.libs/libcurl.a "$output/libcurl-clang.a"
    readelf -d "$output/curl-clang" >"$output/curl-clang.dynamic"

    python3 /work/tests/curl-oracle-differential.py \
      --gcc "$oracle/curl-gcc" --clang "$output/curl-clang" \
      --output "$output/canonical-differential.json"
    cmp "$oracle/tool_ca_embed-gcc.c" "$output/tool_ca_embed-clang.c"
    cmp "$oracle/tool_hugehelp-gcc.c" "$output/tool_hugehelp-clang.c"

    valgrind --leak-check=full --show-leak-kinds=all \
      --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
      --log-file="$output/valgrind-version.log" \
      "$output/curl-clang" --version >"$output/valgrind-version.out"
    printf "rustbox-curl-file-payload\n" >"$output/file-input"
    valgrind --leak-check=full --show-leak-kinds=all \
      --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
      --log-file="$output/valgrind-file.log" \
      "$output/curl-clang" --silent --show-error \
        "file://$output/file-input" >"$output/valgrind-file.out"
    cmp "$output/file-input" "$output/valgrind-file.out"
    chmod -R a+rwX "$source" "$build" "$output"
  '
