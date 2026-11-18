#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
jobs=${RUSTBOX_ANALYZER_JOBS:-16}
timeout=${RUSTBOX_ANALYZER_TIMEOUT:-120}
run_id=${RUSTBOX_ANALYSIS_RUN_ID:-codechecker-coreutils-9.12}

case $jobs in
  *[!0-9]*|'') echo "RUSTBOX_ANALYZER_JOBS must be a positive integer" >&2; exit 2 ;;
esac
case $timeout in
  *[!0-9]*|'') echo "RUSTBOX_ANALYZER_TIMEOUT must be a positive integer" >&2; exit 2 ;;
esac

database="$root/work/analysis/coreutils-9.12/canonical-clang/compile_commands.json"
test -s "$database" || {
  echo "missing canonical compile database; run scripts/capture_coreutils_compdb.sh" >&2
  exit 2
}

exec "$root/scripts/run_tool.sh" sh -eu -c '
  database=/rustbox-coreutils/canonical-clang-compdb/compile_commands.json
  reports=/rustbox-coreutils/analysis/$1
  jobs=$2
  timeout=$3

  test -s "$database"
  if test -e "$reports"; then
    echo "refusing to mix analysis runs in existing directory: $reports" >&2
    echo "choose a fresh RUSTBOX_ANALYSIS_RUN_ID" >&2
    exit 2
  fi

  CodeChecker analyze "$database" \
    --output "$reports" \
    --jobs "$jobs" \
    --analyzers clangsa clang-tidy cppcheck \
    --compile-uniqueing none \
    --report-hash context-free-v2 \
    --timeout "$timeout"
' rustbox-codechecker "$run_id" "$jobs" "$timeout"
