#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
exec docker run --rm --platform linux/amd64 \
  --volume "$root:/work" \
  --volume rustbox-e2fsprogs-1.47.4:/rustbox-e2fsprogs \
  --workdir /work rustbox-e2fsprogs:2026-11-24 sh -eu -c '
    source=/work/work/upstream/e2fsprogs-1.47.4
    volume=/rustbox-e2fsprogs
    evidence=/work/work/analysis/e2fsprogs-1.47.4/oracle

    configure_build()
    {
      compiler=$1
      build=$volume/oracle-$compiler
      stage=$volume/stage-$compiler
      rm -rf "$build" "$stage"
      mkdir -p "$build" "$stage" "$evidence"
      cd "$build"
      CC="$compiler" CFLAGS="-O2 -g -fno-omit-frame-pointer" \
        "$source/configure" \
          --prefix=/usr \
          --with-root-prefix= \
          --enable-fsck \
          --disable-libuuid \
          --disable-libblkid \
          --disable-uuidd \
          --with-systemd-unit-dir=no \
          --with-udev-rules-dir=no \
          --with-crond-dir=no
      bear --output "$evidence/$compiler-compile-commands.json" -- \
        make -j"$(nproc)"
      make install DESTDIR="$stage"
      find "$stage" -type f -perm /111 -printf "%P\n" | sort \
        >"$evidence/$compiler-installed-executables.txt"
      find "$stage" -type l -printf "%P -> %l\n" | sort \
        >"$evidence/$compiler-installed-symlinks.txt"
      find "$stage" -type f -perm /111 -exec file {} + \
        >"$evidence/$compiler-installed-file.txt"
    }

    rm -rf "$evidence"
    mkdir -p "$evidence"
    configure_build gcc >"$evidence/gcc-build.log" 2>&1
    configure_build clang-18 >"$evidence/clang-18-build.log" 2>&1
    chmod -R a+rwX "$evidence"
  '
