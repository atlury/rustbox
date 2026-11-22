#!/bin/sh
# SPDX-License-Identifier: 0BSD
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
base="$root/work/analysis/gawk-5.4.0/translations/c2rust-0.22.1"
audit="$base/gawk-5.4.0-normalized-audit"
complete="$base/gawk-5.4.0-complete"
stable="$base/gawk-5.4.0-stable"

"$root/scripts/combine_gawk_c2rust.py" --input "$audit" --output "$complete"
"$root/scripts/modernize_c2rust_output.py" --input "$complete" --output "$stable"
