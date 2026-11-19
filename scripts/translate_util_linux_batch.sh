#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

test "$#" -ge 2 && test "$#" -le 3 || {
  echo "usage: $0 BATCH audit|reachable [canonical|normalized]" >&2
  exit 2
}
batch=$1
mode=$2
variant=${3:-canonical}
case $batch in *[!A-Za-z0-9_-]*|'') exit 2 ;; esac
case $mode in audit|reachable) ;; *) exit 2 ;; esac
case $variant in canonical|normalized) ;; *) exit 2 ;; esac

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
manifest="$root/batches/$batch.json"
analysis="$root/work/analysis/util-linux-2.42.4"
database="$analysis/canonical-clang/compile_commands.json"
slice="$analysis/slices/$batch/compile_commands.json"
output_name="$batch-$mode"
if test "$variant" = normalized; then
  slice="$analysis/normalized/$batch/compile_commands.json"
  output_name="$batch-normalized-$mode"
fi
output="$analysis/translations/c2rust-0.22.1/$output_name"
test -s "$manifest" || { echo "unknown batch: $batch" >&2; exit 2; }
test -s "$database" || { echo "capture the Clang database first" >&2; exit 1; }

if test "$variant" = canonical; then
  regex=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["output_regex"])' "$manifest")
  expected=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["expected_compile_commands"])' "$manifest")
  "$root/scripts/extract_compdb_slice.py" \
    --database "$database" \
    --output "$slice" \
    --output-regex "$regex" \
    --expected-commands "$expected" \
    --require-unique-sources
else
  test -s "$slice" || { echo "normalize $batch first" >&2; exit 1; }
  integration_slice="$analysis/normalized/$batch/entrypoints/compile_commands.json"
  RUSTBOX_TOOL_IMAGE=rustbox-normalize:2026-11-19 \
    "$root/scripts/run_tool.sh" python3 /work/scripts/specialize_util_linux_entrypoints.py \
      --database "/work/work/analysis/util-linux-2.42.4/normalized/$batch/compile_commands.json" \
      --source-root "/work/work/analysis/util-linux-2.42.4/normalized/$batch/source" \
      --manifest "/work/batches/$batch.json" \
      --output "/work/work/analysis/util-linux-2.42.4/normalized/$batch/entrypoints/compile_commands.json"
  slice="$integration_slice"
fi

case "$output" in
  "$analysis/translations/c2rust-0.22.1/"*)
    test ! -e "$output" || rm -rf -- "$output"
    ;;
  *) exit 2 ;;
esac
mkdir -p "$output"

set -- c2rust transpile \
  "$(printf '%s' "$slice" | sed "s|$root|/work|")" \
  --output-dir "/work/work/analysis/util-linux-2.42.4/translations/c2rust-0.22.1/$output_name" \
  --emit-build-files \
  --emit-c-decl-map \
  --fail-on-error \
  --disable-rustfmt \
  --overwrite-existing
if test "$mode" = audit; then
  set -- "$@" --preserve-unused-functions
fi

RUSTBOX_TOOL_IMAGE=rustbox-normalize:2026-11-19 \
  exec "$root/scripts/run_tool.sh" "$@"
