#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
run_id=${RUSTBOX_ANALYSIS_RUN_ID:-codechecker-coreutils-9.12}
host_output="$root/work/analysis/coreutils-9.12/codechecker-summary"
mkdir -p "$host_output"

"$root/scripts/run_tool.sh" sh -eu -c '
  reports=/rustbox-coreutils/analysis/$1
  export=/work/work/analysis/coreutils-9.12/codechecker-summary/reports.json
  test -d "$reports"
  status=0
  CodeChecker parse --export json --output "$export" "$reports" >/dev/null || status=$?
  test "$status" -eq 0 || test "$status" -eq 2
  python3 /work/scripts/summarize_codechecker.py \
    --export "$export" \
    --reports "$reports" \
    --expected-actions 1689 \
    --output /work/work/analysis/coreutils-9.12/codechecker-summary/summary.json
' rustbox-codechecker-summary "$run_id"

cp "$host_output/summary.json" "$root/evidence/coreutils-9.12-static-analysis.json"
