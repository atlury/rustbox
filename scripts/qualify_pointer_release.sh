#!/bin/sh
# SPDX-License-Identifier: GPL-3.0-or-later
# Build and verify one substitution against the saved parent link.
set -eu
if [ "$#" -lt 3 ] || [ "$#" -gt 4 ]; then
    echo "usage: $0 --iproute2-netlink-protocols|--curl-manual|--tar-borrowed-timestamps PARENT_LINK NEW_DIRECTORY [PARENT_REPLAYS]" >&2
    exit 2
fi
case "$1" in
    --iproute2-netlink-protocols|--curl-manual|--tar-borrowed-timestamps) selection=$1 ;;
    *) echo "unsupported pointer substitution: $1" >&2; exit 2 ;;
esac
root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
parent=$2
out=$3
replays=${4:-}
live=$root/work/analysis/rustbox-multicall-link.json
cmp "$parent" "$live"
mkdir "$out"
"$root/scripts/build_rustbox_multicall.sh" "$selection" > "$out/build.log" 2>&1
cp "$live" "$out/release.json"
docker run --rm --network none --platform linux/amd64 \
    -v rustbox-coreutils-9.12:/rustbox-coreutils:ro rustbox-e2fsprogs:2026-11-24 \
    cat /rustbox-coreutils/canonical-clang-no-security-compdb/src/rustbox > "$out/rustbox"
chmod +x "$out/rustbox"

set -- "$parent" "$out/rustbox" "$out/verified" --jobs 4
if [ -n "$replays" ]; then
    python3 - "$parent" "$replays" "$out/address-copies.json" <<'PY'
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
    set -- "$@" --copy-replay "$out/address-copies.json"
fi
python3 -B "$root/scripts/verify_dirhash_release.py" "$@" > "$out/verification.log" 2>&1
python3 -B "$root/scripts/rank_foreign_declarations.py" "$out/release.json" > "$out/foreign.json"
python3 -B "$root/scripts/rank_fixed_array_helpers.py" "$out/release.json" > "$out/fixed-arrays.json"
python3 -B "$root/scripts/rank_shared_applet_modules.py" "$out/release.json" --limit 20 > "$out/shared-modules.json"
python3 -B "$root/scripts/rank_shared_applet_modules.py" "$out/release.json" --tables --limit 20 > "$out/name-tables.json"
python3 -B "$root/scripts/record_pointer_release.py" "$out/rustbox" "$out/verified" "$out"
