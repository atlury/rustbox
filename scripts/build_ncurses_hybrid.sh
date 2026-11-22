#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-tar:2026-11-22 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    crate=/work/work/analysis/ncurses-6.6/translations/c2rust-0.22.1/ncurses-6.6-normalized-audit-stable
    archive=$crate/target/release/libncurses_6_6_normalized_audit.a
    output=/rustbox-ncurses/hybrid
    evidence=/work/work/analysis/ncurses-6.6/hybrid
    canonical=/work/work/analysis/ncurses-6.6/normalized/gcc-root
    rm -rf "$output" "$evidence"
    mkdir -p "$output/usr/bin" "$output/usr/share" "$evidence"

    cd "$crate"
    cargo build --release >"$evidence/cargo-build.log" 2>&1
    nm -g --defined-only "$archive" >"$evidence/archive.symbols"
    size -A "$archive" >"$evidence/archive.sections"

    set -- \
      clear rustbox_clear_main \
      infocmp rustbox_infocmp_main \
      tabs rustbox_tabs_main \
      tic rustbox_tic_main \
      toe rustbox_toe_main \
      tput rustbox_tput_main \
      tset rustbox_tset_main
    while test "$#" -gt 0; do
      name=$1
      entry=$2
      shift 2
      binary=$output/usr/bin/$name
      clang-18 -O2 -g -fno-omit-frame-pointer \
        -ffunction-sections -fdata-sections -DRUSTBOX_ENTRY=$entry \
        -Wl,--gc-sections -Wl,-Map,"$evidence/$name.map" \
        -o "$binary" /work/bridges/ncurses_main.c "$archive" \
        -ldl -lpthread -lm -lrt -lutil
      cp "$binary" "$evidence/$name"
      cp "$binary" "$evidence/$name.stripped"
      strip --strip-all "$evidence/$name.stripped"
      readelf -d "$binary" >"$evidence/$name.dynamic"
      size -A "$binary" >"$evidence/$name.sections"
      nm -g --defined-only "$binary" >"$evidence/$name.symbols"
    done

    ln -s tic "$output/usr/bin/captoinfo"
    ln -s tic "$output/usr/bin/infotocap"
    ln -s tset "$output/usr/bin/reset"
    cp "$canonical/usr/bin/ncursesw6-config" "$output/usr/bin/ncursesw6-config"
    cp -a "$canonical/usr/share/terminfo" "$output/usr/share/terminfo"

    python3 /work/tests/ncurses-oracle-differential.py \
      --gcc-root "$canonical" --clang-root "$output" \
      --output "$evidence/differential.json"

    for name in captoinfo clear infocmp infotocap tabs tic toe tput tset reset; do
      TERM=xterm TERMINFO="$output/usr/share/terminfo" \
        valgrind --leak-check=full --show-leak-kinds=all \
          --errors-for-leak-kinds=definite,indirect,possible --error-exitcode=99 \
          --log-file="$evidence/valgrind-$name.log" \
          "$output/usr/bin/$name" -V \
          >"$evidence/valgrind-$name.out" 2>&1
      grep -q "ERROR SUMMARY: 0 errors" "$evidence/valgrind-$name.log"
      grep -Eq "All heap blocks were freed|definitely lost: 0 bytes" \
        "$evidence/valgrind-$name.log"
      grep -Eq "All heap blocks were freed|indirectly lost: 0 bytes" \
        "$evidence/valgrind-$name.log"
      grep -Eq "All heap blocks were freed|possibly lost: 0 bytes" \
        "$evidence/valgrind-$name.log"
    done
  '
