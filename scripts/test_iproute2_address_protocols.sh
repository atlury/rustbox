#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
set -eu
root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
docker run --rm -i --network none --platform linux/amd64 --tmpfs /etc/iproute2 --tmpfs /usr/share/iproute2 \
    -v "$root:/work:ro" --workdir /tmp rustbox-e2fsprogs:2026-11-24 sh -seu <<'CHECK'
export LC_ALL=C TZ=UTC
base=/work/work/analysis/iproute2-7.3.0
src=/work/work/upstream/iproute2-7.3.0
(cd "$src" && sha256sum -c <<'HASHES'
c7a7fbcfc2995b82fe50b8afd839311e45126e1d3dc135b732988c158f7ec77e  lib/rt_names.c
b8223569a65254ecd3ea34c0368b253e355f558c270e246fdb7c240823b29414  include/rt_names.h
HASHES
)
python3 -B - "$base/oracle/gcc-compile-commands.json" "$src" <<'BUILD'
from pathlib import Path
import json, subprocess, sys
src = Path(sys.argv[2])
record, = (r for r in json.load(open(sys.argv[1])) if r["file"].endswith("/rt_names.c"))
args = record["arguments"][:]
args[args.index("-o") + 1] = "/tmp/rt_names.o"
subprocess.run([*args, "-ffunction-sections", "-fdata-sections"], cwd=src / "lib", check=True)
BUILD
archive=$(PYTHONPATH=/work/scripts python3 -B - <<'ARCHIVE'
from pathlib import Path
import json
from check_cargo_private_inlines import digest
link = json.loads(Path("/work/work/analysis/rustbox-multicall-link.json").read_bytes())
name, = (k for k in link["source_library_sha256"] if k.endswith("/libip_audit.a"))
archive = Path("/work") / name
if digest(archive) != link["source_library_sha256"][name]:
    raise ValueError("IPRoute2 ip archive differs from the link")
print(archive)
ARCHIVE
)
gcc -O2 -Wall -Wextra -Werror -I"$src/include" -c /work/tests/iproute2-address-protocols/compare.c -o compare.o
gcc -Wl,--gc-sections compare.o rt_names.o -o canonical
gcc -Wl,--gc-sections compare.o "$archive" -lmnl -lbpf -lelf -lz -ldl -lm -lpthread -o translated
python3 -B /work/tests/iproute2-address-protocols/configuration.py
CHECK
