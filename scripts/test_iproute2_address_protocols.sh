#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
set -eu
root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
case "$#" in
    0) set -- ;;
    1) test "$1" = --pilot || exit 2; set -- -e RUSTBOX_ADDRPROT_PILOT=1 ;;
    2) test "$1" = --archive || exit 2
       pilot=$(CDPATH= cd -- "$2" && pwd)
       set -- -e RUSTBOX_ADDRPROT_FULL=1 -v "$pilot:/pilot:ro" -v rustbox-iproute2-7.3.0:/rustbox-iproute2:ro \
           -v rustbox-coreutils-9.12:/rustbox-coreutils:ro ;;
    *) exit 2 ;;
esac
docker run --rm -i --network none "$@" --platform linux/amd64 --tmpfs /etc/iproute2 --tmpfs /usr/share/iproute2 \
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
set -- translated
if [ "${RUSTBOX_ADDRPROT_PILOT:-0}" = 1 ]; then
    python3 -B /work/scripts/stage_iproute2_address_protocols.py /work/work/analysis/rustbox-multicall-link.json /tmp
    for variant in control candidate; do
        rustc --edition=2021 --crate-name rt_names --crate-type=staticlib -C opt-level=s -C panic=abort \
            --cap-lints=allow "$variant.rs" -o "$variant.a"
        gcc -Wl,--gc-sections compare.o "$variant.a" -ldl -lpthread -lm -o "$variant"
    done
    set -- "$@" control candidate candidate-memcheck
fi
if [ "${RUSTBOX_ADDRPROT_FULL:-0}" = 1 ]; then
    python3 -B - "$archive" <<'VERIFY'
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
record = json.loads(Path("/pilot/pilot.json").read_bytes())
control = Path(sys.argv[1])
release = json.loads(Path("/work/work/analysis/rustbox-multicall-link.json").read_bytes())
binary = Path("/rustbox-coreutils/canonical-clang-no-security-compdb/src/rustbox")
if (str(control.relative_to("/work")) != record["archive"] or sha256(control.read_bytes()).hexdigest() != record["control_sha256"]
        or sha256(Path("/pilot/libip_audit.a").read_bytes()).hexdigest() != record["candidate_sha256"]
        or sha256(binary.read_bytes()).hexdigest() != release["binary"]["sha256"] or release["binary"]["sha256"] != record["control_binary_sha256"]):
    raise ValueError("pilot archive differs from the recorded Cargo build")
symbols = {line.split()[-1] for line in subprocess.check_output(["nm", "--defined-only", binary], text=True).splitlines() if line.strip()}
for name in ("rtnl_addrprot_a2n", "rtnl_addrprot_n2a"):
    owners = sorted(engine for engine, renamed in release["iproute2_namespaced_symbols"].items()
                    if name in renamed and f"rustbox_iproute2_{engine}_private_{name}" in symbols)
    if owners != ["ip"]:
        raise ValueError(("address-protocol ELF symbol owners changed", name, owners))
print("Only the ip namespace emits the two address-protocol function symbols in the current multicall ELF.")
VERIFY
    gcc -Wl,--gc-sections compare.o /pilot/libip_audit.a -lmnl -lbpf -lelf -lz -ldl -lm -lpthread -o complete
    for executable in ip-control ip; do
        library=$archive
        if [ "$executable" = ip ]; then library=/pilot/libip_audit.a; fi
        clang-18 -O2 -Wl,--gc-sections -DRUSTBOX_IPROUTE2_ENTRY=rustbox_iproute2_ip_main \
            /work/bridges/iproute2_program_main.c "$library" \
            -ltirpc -lbpf -lelf -lmnl -lcap -ldb -lxtables -ldl -lpthread -lm -o "/tmp/$executable"
        strip --strip-all -o "/tmp/$executable.stripped" "/tmp/$executable"
    done
    set -- "$@" complete complete-memcheck
fi
python3 -B /work/tests/iproute2-address-protocols/configuration.py "$@"
if [ "${RUSTBOX_ADDRPROT_FULL:-0}" = 1 ]; then
    python3 -B /work/tests/iproute2-address-protocols/command.py /rustbox-iproute2/programs-gcc/ip /tmp/ip-control /tmp/ip
    python3 -B - "$src" <<'REPORT'
import hashlib, json, sys
from pathlib import Path
src = Path(sys.argv[1])
result = json.loads(Path("/pilot/pilot.json").read_bytes())
result["canonical_source_sha256"] = {name: hashlib.sha256((src / name).read_bytes()).hexdigest()
                                    for name in ("lib/rt_names.c", "include/rt_names.h")}
result["control_elf_address_protocol_symbol_owners"] = ["ip"]
result["lookup_checks"] = json.loads(Path("/tmp/addrprot-lookups.json").read_bytes())
result["command_checks"] = json.loads(Path("/tmp/addrprot-commands.json").read_bytes())
result["standalone_ip"] = {name: {"stripped_bytes": path.stat().st_size, "stripped_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                           for name, path in (("control", Path("/tmp/ip-control.stripped")), ("candidate", Path("/tmp/ip.stripped")))}
print(json.dumps(result, sort_keys=True))
REPORT
fi
CHECK
