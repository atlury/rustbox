#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# Build and verify one substitution against the saved parent link.
set -eu
resume=
if [ "${1:-}" = --resume-built ]; then
    resume=1
    shift
fi
if [ "$#" -lt 3 ] || [ "$#" -gt 4 ]; then
    echo "usage: $0 [--resume-built] SELECTION PARENT_LINK BUILD_DIRECTORY [PARENT_REPLAYS]" >&2
    exit 2
fi
case "$1" in
    --iproute2-netlink-protocols|--curl-manual|--tar-borrowed-timestamps|--bison-literal-lengths|--iproute2-routing-protocols|--lz4-benchmark-dictionary) selection=$1 ;;
    *) echo "unsupported pointer substitution: $1" >&2; exit 2 ;;
esac
root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
parent=$2
out=$3
replays=${4:-}
live=$root/work/analysis/rustbox-multicall-link.json
results=$out
if [ -n "$resume" ]; then
    cmp "$out/release.json" "$live"
    if [ -f "$out/parent.json" ]; then
        cmp "$out/parent.json" "$parent"
    else
        cmp "$out/verified/control.json" "$parent"
    fi
    if [ -f "$out/verified/release.json" ]; then
        cmp "$out/verified/release.json" "$live"
    fi
    python3 - "$selection" "$parent" "$live" "$out/rustbox" <<'PY'
from hashlib import sha256
import json
from pathlib import Path
import sys
field = sys.argv[1][2:].replace("-", "_")
parent, release, binary = map(Path, sys.argv[2:])
before, after = (json.loads(p.read_bytes()) for p in (parent, release))
if not after.get(field) or after[field] == before.get(field):
    raise ValueError("saved build does not contain the requested substitution")
if sha256(binary.read_bytes()).hexdigest() != after["binary"]["sha256"]:
    raise ValueError("saved executable differs from the linked release")
PY
    results=$(mktemp -d "$out/retry.XXXXXX")
else
    cmp "$parent" "$live"
    mkdir "$out"
    cp "$parent" "$out/parent.json"
    "$root/scripts/build_rustbox_multicall.sh" "$selection" > "$out/build.log" 2>&1
    cp "$live" "$out/release.json"
    docker run --rm --network none --platform linux/amd64 \
        -v rustbox-coreutils-9.12:/rustbox-coreutils:ro rustbox-e2fsprogs:2026-11-24 \
        cat /rustbox-coreutils/canonical-clang-no-security-compdb/src/rustbox > "$out/rustbox"
    chmod +x "$out/rustbox"
fi

set -- "$parent" "$out/rustbox" "$results/verified" --jobs 4
if [ -n "$resume" ] && [ -s "$out/verified/independent/results.json" ]; then
    if python3 - "$out/verified/independent/results.json" <<'PY'
import json, sys
from pathlib import Path
statuses = json.loads(Path(sys.argv[1]).read_bytes())["statuses"]
sys.exit(0 if statuses and all(type(s) is int and s == 0 for s in statuses.values()) else 1)
PY
    then
        set -- "$@" --independent-replay "$out/verified/independent/results.json"
    fi
fi
if [ -n "$replays" ]; then
    python3 - "$parent" "$replays" "$results/address-copies.json" <<'PY'
from hashlib import sha256
import json
from pathlib import Path
import sys
link, previous, target = map(Path, sys.argv[1:])
replay = json.loads(previous.read_bytes())
if sha256(link.read_bytes()).hexdigest() != replay["link_report_sha256"]:
    raise ValueError("address-protocol replay belongs to a different parent link")
target.write_text(json.dumps(replay["iproute2_address_protocol_copies"], sort_keys=True) + "\n")
PY
    set -- "$@" --copy-replay "$results/address-copies.json"
fi
python3 -B "$root/scripts/verify_dirhash_release.py" "$@" > "$results/verification.log" 2>&1
python3 -B "$root/scripts/rank_foreign_declarations.py" "$out/release.json" > "$out/foreign.json"
python3 -B "$root/scripts/rank_fixed_array_helpers.py" "$out/release.json" > "$out/fixed-arrays.json"
python3 -B "$root/scripts/rank_shared_applet_modules.py" "$out/release.json" --limit 20 > "$out/shared-modules.json"
python3 -B "$root/scripts/rank_shared_applet_modules.py" "$out/release.json" --tables --limit 20 > "$out/name-tables.json"
python3 -B "$root/scripts/record_pointer_release.py" "$out/rustbox" "$results/verified" "$out"
