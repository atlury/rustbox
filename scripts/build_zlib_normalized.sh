#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-normalize:2026-11-19 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    source=/work/work/analysis/zlib-1.4/normalized/source
    analysis=/work/work/analysis/zlib-1.4/normalized
    gcc_build=$analysis/gcc-cmake
    clang_build=$analysis/clang-make
    sanitize_build=$analysis/gcc-sanitize

    test -f "$analysis/normalization.json"
    cmake --fresh -S "$source" -B "$gcc_build" -G Ninja \
      -DCMAKE_BUILD_TYPE=RelWithDebInfo \
      -DCMAKE_C_COMPILER=gcc \
      -DCMAKE_EXPORT_COMPILE_COMMANDS=ON \
      -DZLIB_BUILD_TESTING=ON \
      -DZLIB_BUILD_SHARED=ON \
      -DZLIB_BUILD_STATIC=ON
    cmake --build "$gcc_build" --target clean
    cmake --build "$gcc_build" --parallel "$(nproc)"
    ctest --test-dir "$gcc_build" --output-on-failure --parallel "$(nproc)"

    mkdir -p "$clang_build"
    cd "$clang_build"
    CC=clang-18 CFLAGS="-O2 -g -fno-omit-frame-pointer" "$source/configure"
    bear --output compile_commands.json -- make -B -j"$(nproc)"
    make test
    make test64

    mkdir -p "$sanitize_build"
    cd "$sanitize_build"
    CC=gcc \
      CFLAGS="-O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer" \
      LDFLAGS="-fsanitize=address,undefined" \
      "$source/configure" --static
    make -B -j"$(nproc)"
    ASAN_OPTIONS=detect_leaks=1:halt_on_error=1 \
      UBSAN_OPTIONS=halt_on_error=1 make test
    ASAN_OPTIONS=detect_leaks=1:halt_on_error=1 \
      UBSAN_OPTIONS=halt_on_error=1 make test64

    case_dir=$(mktemp -d)
    cd "$case_dir"
    valgrind --quiet --leak-check=full --show-leak-kinds=all \
      --errors-for-leak-kinds=all --error-exitcode=99 \
      "$gcc_build/test/zlib_example" example.gz
    valgrind --quiet --leak-check=full --show-leak-kinds=all \
      --errors-for-leak-kinds=all --error-exitcode=99 \
      "$gcc_build/test/infcover"
  '
