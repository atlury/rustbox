#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
workspace=/work/work/analysis/gawk-5.4.0/translations/c2rust-0.22.1/gawk-5.4.0-extensions
log=/work/work/analysis/gawk-5.4.0/translations/c2rust-0.22.1/extensions-cargo-release.log

test -s "$root/work/analysis/gawk-5.4.0/translations/c2rust-0.22.1/gawk-5.4.0-extensions/Cargo.toml" || {
  echo "run scripts/prepare_gawk_extensions.sh first" >&2
  exit 1
}

RUSTBOX_TOOL_IMAGE=rustbox-gawk:2026-11-22 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    cd "$1"
    RUSTUP_TOOLCHAIN=1.99.0 cargo generate-lockfile >"$2" 2>&1
    RUSTUP_TOOLCHAIN=1.99.0 cargo build --workspace --release --locked >>"$2" 2>&1
    for name in filefuncs fnmatch fork inplace intdiv ordchr readdir readfile \
      revoutput revtwoway rwarray testext time; do
      library=target/release/lib$name.so
      test -s "$library"
      nm -D --defined-only "$library" >"target/release/$name.symbols"
      test "$(grep -c " T dl_load$" "target/release/$name.symbols")" -eq 1
      test "$(grep -c " [BD] plugin_is_GPL_compatible$" \
        "target/release/$name.symbols")" -eq 1
    done
  ' sh "$workspace" "$log"
