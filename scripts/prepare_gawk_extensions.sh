#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
base="$root/work/analysis/gawk-5.4.0/translations/c2rust-0.22.1"
audit="$base/gawk-5.4.0-normalized-audit"
raw="$base/gawk-5.4.0-extensions"

"$root/scripts/prepare_gawk_extensions.py" --input "$audit" --output "$raw"
for crate in "$raw"/*; do
  test -d "$crate" || continue
  name=$(basename "$crate")
  "$root/scripts/modernize_c2rust_output.py" \
    --input "$crate" --output "$raw/$name-stable" >/dev/null
done
members=$(find "$raw" -mindepth 1 -maxdepth 1 -type d -name '*-stable' \
  -exec basename {} \; \
  | LC_ALL=C sort | sed 's/.*/"&"/' | paste -sd, -)
printf '[workspace]\nresolver = "2"\nmembers = [%s]\n' "$members" \
  >"$raw/Cargo.toml"
