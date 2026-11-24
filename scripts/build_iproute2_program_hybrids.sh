#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
RUSTBOX_TOOL_IMAGE=rustbox-iproute2:2026-11-24 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    base=/work/work/analysis/iproute2-7.3.0/program-translations
    output=/rustbox-iproute2/program-hybrids
    evidence=/work/work/analysis/iproute2-7.3.0/program-hybrids
    programs="arpd bridge dcb devlink dpll genl ifstat ip lnstat netshaper nstat rdma rtacct rtmon ss tc tipc vdpa"

    rm -rf "$output" "$evidence"
    mkdir -p "$output" "$evidence"
    for name in $programs; do
      archive=$base/cargo-target/$name/release/lib${name}_audit.a
      crate=$base/$name/$name-final
      test -f "$archive"
      test -f "$crate/rustbox-cargo-check.json"
      python3 - "$crate/rustbox-cargo-check.json" <<'\''PY'\''
import json, sys
record = json.load(open(sys.argv[1]))
assert record["exit_status"] == 0
assert record["build_finished_success"] is True
assert not record["errors"]
PY
      clang-18 -O2 -g -fno-omit-frame-pointer \
        -ffunction-sections -fdata-sections -Wl,--gc-sections \
        -Wl,-Map,"$evidence/$name.map" \
        -DRUSTBOX_IPROUTE2_ENTRY=rustbox_iproute2_${name}_main \
        -o "$output/$name" /work/bridges/iproute2_program_main.c \
        "$archive" \
        -ltirpc -lbpf -lelf -lmnl -lcap -ldb -lxtables \
        -ldl -lpthread -lm
      nm -g --defined-only "$output/$name" >"$evidence/$name.symbols"
      test "$(awk -v symbol="rustbox_iproute2_${name}_main" \
        '\''$NF == symbol { n++ } END { print n+0 }'\'' \
        "$evidence/$name.symbols")" -eq 1
    done
    chmod -R a+rwX "$output" "$evidence"
  '
