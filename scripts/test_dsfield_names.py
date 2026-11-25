#!/usr/bin/env python3
"""Compare all five DS field and DSCP interfaces with canonical IPRoute2 and repeat read-only ip filters."""
# SPDX-License-Identifier: GPL-2.0-or-later
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess

from check_cargo_private_inlines import ROOT, digest
from test_iproute2_route_names import SOURCE, capture, run
from test_routing_protocol_pilot import LIBS

DRIVER = ROOT / "tests/iproute2-dsfield/lookups.c"


PROFILES = ("empty", "vendor", "local", "malformed")
QUERIES = ("0", "10", "ff", "0x100", "vendor", "local", "first", "dup", "missing")


def configure(profile, local, vendor):
    if profile in ("vendor", "local"):
        folder = local if profile == "local" else vendor
        (folder / "rt_dsfield").write_bytes(b"0 " + profile.encode() + b"\n24 dup\n8 dup\n255 raw-\xff\n")
    elif profile == "malformed":
        (local / "rt_dsfield").write_bytes(b"44 first\nbad-line\n48 ignored\n")


def canonical_drivers():
    run("gcc", "-O2", "-Wall", "-Wextra", "-Werror", "-I" + str(SOURCE / "include"), "-c", DRIVER, "-o", "driver.o")
    for cc in ("gcc", "clang-18"):
        db = json.loads((ROOT / f"work/analysis/iproute2-7.3.0/oracle/{cc}-compile-commands.json").read_bytes())
        objects = []
        for name in ("rt_names", "utils"):
            args, = [r["arguments"] for r in db if r["file"].endswith(f"/lib/{name}.c")]
            obj = Path.cwd() / (cc + "-" + name + ".o")
            args[args.index("-o") + 1] = str(obj)
            run(*args, "-ffunction-sections", "-fdata-sections", cwd=SOURCE / "lib")
            objects.append(obj)
        run(cc, "-Wl,--gc-sections", "driver.o", *objects, "-o", "oracle-" + cc)


def compare(pilot, link_file):
    link = json.loads(link_file.read_bytes())
    row = json.loads((pilot / "pilot.json").read_bytes())
    key = row["archive"]
    before, after = ROOT / key, pilot / Path(key).name
    if (row["control_sha256"] != link["source_library_sha256"][key] or row["control_binary_sha256"] != link["binary"]["sha256"]
            or digest(before) != row["control_sha256"] or digest(after) != row["candidate_sha256"]
            or digest(SOURCE / "lib/rt_names.c") != row["canonical_sha256"]):
        raise ValueError("the canonical source, compiler parent or candidate archive differs")
    canonical_drivers()
    ip = before.name == "libip_audit.a"
    oracle_hashes = {}
    if ip:
        pinned = json.loads((ROOT / "evidence/iproute2-routing-protocol-multicall.json").read_bytes())["canonical"]
        for cc in ("gcc", "clang-18"):
            checksum = digest(Path(f"/rustbox-iproute2/programs-{cc}/ip"))
            if checksum != pinned[cc]["canonical_sha256"]["ip"]:
                raise ValueError(f"the canonical {cc} ip executable changed")
            oracle_hashes[cc] = checksum
    for title, library in (("control", before), ("candidate", after)):
        run("gcc", "-Wl,--gc-sections", "driver.o", library, *LIBS, "-o", title)
        if ip:
            run("gcc", "-Wl,--gc-sections", "-DRUSTBOX_IPROUTE2_ENTRY=rustbox_iproute2_ip_main",
                ROOT / "bridges/iproute2_program_main.c", library, *LIBS, "-o", title + "-ip")
    local, vendor = Path("/etc/iproute2"), Path("/usr/share/iproute2")
    if not all(os.path.ismount(p) and not any(p.iterdir()) for p in (local, vendor)):
        raise ValueError("expected empty private configuration mounts")
    profiles = []
    for profile in PROFILES:
        configure(profile, local, vendor)
        expected = capture(["./oracle-gcc"])
        lines = expected[1].splitlines()
        counts = {prefix.decode(): sum(s.startswith(prefix + b" ") for s in lines) for prefix in (b"N", b"F", b"R")}
        label = profile.encode() if profile in ("local", "vendor") else b"0"
        retained = b"loaded " + label + b" retained 0 identical " + (b"1" if label == b"0" else b"0")
        if (expected[0] or bool(expected[2]) != (profile == "malformed") or b"first 0" not in lines or retained not in lines
                or counts != dict(N=258, F=4552, R=634)):
            raise ValueError(("unexpected canonical lookup coverage", profile, counts, retained))
        for argv in (["./oracle-clang-18"], ["./control"], ["./candidate"],
                     ["valgrind", "--leak-check=no", "--error-exitcode=91", "--log-file=memcheck.log", "./candidate"]):
            actual = capture(argv)
            if actual != expected:
                first = next(((a, b) for a, b in zip(lines, actual[1].splitlines()) if a != b), None)
                raise ValueError((profile, argv, actual[0], actual[2], first))
        if "ERROR SUMMARY: 0 errors" not in Path("memcheck.log").read_text():
            raise ValueError("DS field memory check failed")
        statuses = []
        for query in QUERIES if ip else ():
            argv = ["ip", "-4", "route", "show", "tos", query]
            control = capture(argv, executable="/rustbox-iproute2/programs-gcc/ip")
            for program in ("/rustbox-iproute2/programs-clang-18/ip", "./control-ip", "./candidate-ip"):
                if capture(argv, executable=program) != control:
                    raise ValueError(("public route filter differs", profile, query, program))
            statuses.append(control[0])
        if ip and not 0 < statuses.count(0) < len(statuses):
            raise ValueError("expected accepted and rejected public route filters")
        profiles.append(dict(profile=profile, counts=counts, stdout_sha256=sha256(expected[1]).hexdigest(),
                             stderr_sha256=sha256(expected[2]).hexdigest(), public_filter_status=statuses))
    inputs = ("lib/utils.c", "lib/rt_names.c", "include/rt_names.h")
    return dict(row, profiles=profiles, driver_sha256=digest(DRIVER), memcheck_runs=len(profiles),
                oracle_compilers=["gcc", "clang-18"], public_oracle_sha256=oracle_hashes,
                canonical_inputs={name: digest(SOURCE / name) for name in inputs})


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("pilot", type=Path)
    p.add_argument("link", type=Path)
    p.add_argument("--mounted", action="store_true")
    args = p.parse_args()
    if args.mounted:
        print(json.dumps(compare(args.pilot, args.link), indent=2, sort_keys=True))
    else:
        paths = [Path("/work") / path.resolve().relative_to(ROOT) for path in (args.pilot, args.link)]
        subprocess.run(["docker", "run", "--rm", "--network", "none", "--platform", "linux/amd64",
                        "-v", f"{ROOT}:/work:ro", "-v", "rustbox-iproute2-7.3.0:/rustbox-iproute2:ro",
                        "--tmpfs", "/etc/iproute2", "--tmpfs", "/usr/share/iproute2", "-w", "/tmp",
                        "rustbox-e2fsprogs:2026-11-24", "python3", "-B", "/work/scripts/test_dsfield_names.py",
                        *paths, "--mounted"], check=True)
