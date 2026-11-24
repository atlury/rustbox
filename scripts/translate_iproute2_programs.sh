#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
set -eu

root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
analysis="$root/work/analysis/iproute2-7.3.0"
base="$analysis/program-translations"
programs="arpd bridge dcb devlink dpll genl ifstat ip lnstat netshaper nstat rdma rtacct rtmon ss tc tipc vdpa"

test -f "$analysis/program-closures/engines/closure-counts.json"
mkdir -p "$base"
for name in $programs; do
	program="$base/$name"
	audit="$program/$name-audit"
	case "$audit" in
		"$base"/*/*-audit) test ! -e "$audit" || rm -rf -- "$audit" ;;
		*) exit 2 ;;
	esac
	mkdir -p "$program"
done

# Each C2Rust process is deliberately single-threaded.  Four independent
# exact program closures run concurrently; this avoids the unsafe monolithic
# merge while still using the available cores.
RUSTBOX_TOOL_IMAGE=rustbox-iproute2:2026-11-24 \
  "$root/scripts/run_tool.sh" sh -eu -c '
    base=/work/work/analysis/iproute2-7.3.0/program-translations
    closures=/work/work/analysis/iproute2-7.3.0/program-closures/engines
    export base closures
    printf "%s\n" arpd bridge dcb devlink dpll genl ifstat ip lnstat \
      netshaper nstat rdma rtacct rtmon ss tc tipc vdpa |
      xargs -n 1 -P 4 sh -eu -c '\''
        name=$1
        output=$base/$name/$name-audit
        RAYON_NUM_THREADS=1 c2rust transpile \
          "$closures/$name/compile_commands.json" \
          --output-dir "$output" \
          --emit-build-files --fail-on-error --disable-rustfmt \
          --overwrite-existing --preserve-unused-functions \
          >"$base/$name/transpile.log" 2>&1
      '\'' sh
    chmod -R a+rwX "$base"
  '

for name in $programs; do
	program="$base/$name"
	python3 -B "$root/scripts/modernize_c2rust_output.py" \
		--input "$program/$name-audit" --output "$program/$name-stable" \
		>"$program/modernize.log"
	python3 -B "$root/scripts/finalize_iproute2_stable.py" \
		--program "$name" --input "$program/$name-stable" \
		--output "$program/$name-final" >"$program/finalize.log"
done

RUSTBOX_TOOL_IMAGE=rustbox-iproute2:2026-11-24 \
  exec "$root/scripts/run_tool.sh" sh -eu -c '
    base=/work/work/analysis/iproute2-7.3.0/program-translations
    export base
    printf "%s\n" arpd bridge dcb devlink dpll genl ifstat ip lnstat \
      netshaper nstat rdma rtacct rtmon ss tc tipc vdpa |
      xargs -n 1 -P 4 sh -eu -c '\''
        name=$1
        crate=$base/$name/$name-final
        export CARGO_TARGET_DIR=$base/cargo-target/$name
        python3 /work/scripts/check_cargo_crate.py \
          --crate "$crate" --output "$crate/rustbox-cargo-check.json" \
          >"$base/$name/cargo-check.log" 2>&1
        cargo build --manifest-path "$crate/Cargo.toml" --release \
          >"$base/$name/cargo-build.log" 2>&1
      '\'' sh
    chmod -R a+rwX "$base"
  '
