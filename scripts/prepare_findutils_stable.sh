#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
base="$root/work/analysis/findutils-4.10.0/translations/c2rust-0.22.1"
audit="$base/findutils-4.10.0-normalized-audit"
complete="$base/findutils-4.10.0-complete"
complete_stable="$base/findutils-4.10.0-complete-stable"
reachable="$base/findutils-4.10.0-reachable"
stable="$base/findutils-4.10.0-stable"

"$root/scripts/combine_findutils_c2rust.py" --input "$audit" --output "$complete"
"$root/scripts/modernize_c2rust_output.py" --input "$complete" --output "$complete_stable"
"$root/scripts/combine_findutils_c2rust.py" --input "$audit" --output "$reachable" \
  --exclude printf_args --exclude printf_parse --exclude vasnprintf
"$root/scripts/modernize_c2rust_output.py" --input "$reachable" --output "$stable"
