#!/usr/bin/env python3
"""Compare routing protocol lookup, config overlays and read-only ip commands with canonical IPRoute2."""
# SPDX-License-Identifier: GPL-2.0-or-later
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess

from check_cargo_private_inlines import ROOT, digest
from test_iproute2_route_names import SOURCE, capture, run

DRIVER = ROOT / "tests/iproute2-netlink-protocols/lookups.c"
LIBS = "-ltirpc -lbpf -lelf -lmnl -lcap -ldb -lxtables -ldl -lpthread -lm".split()


def compare(pilot, link_path):
    row = json.loads((pilot / "pilot.json").read_bytes())
    link = json.loads(link_path.read_bytes())
    key = row["archive"]
    parent, candidate = ROOT / key, pilot / Path(key).name
    if (digest(parent) != row["control_sha256"] or digest(candidate) != row["candidate_sha256"]
            or row["control_binary_sha256"] != link["binary"]["sha256"] or link["source_library_sha256"][key] != digest(parent)):
        raise ValueError("routing protocol pilot differs from its selected release")
    source = SOURCE / "lib/rt_names.c"
    if digest(source) != "c7a7fbcfc2995b82fe50b8afd839311e45126e1d3dc135b732988c158f7ec77e":
        raise ValueError("canonical routing protocol source differs")
    run("gcc", "-O2", "-Wall", "-Wextra", "-Werror", "-I" + str(SOURCE / "include"),
        "-Dnl_proto_n2a=rtnl_rtprot_n2a", "-Dnl_proto_a2n=rtnl_rtprot_a2n", "-c", DRIVER, "-o", "driver.o")
    for cc in ("gcc", "clang-18"):
        db = ROOT / f"work/analysis/iproute2-7.3.0/oracle/{cc}-compile-commands.json"
        args, = [r["arguments"] for r in json.loads(db.read_bytes()) if r["file"].endswith("/rt_names.c")]
        obj = "/tmp/oracle-" + cc + ".o"
        args[args.index("-o") + 1] = obj
        run(*args, "-ffunction-sections", "-fdata-sections", cwd=source.parent)
        run(cc, "-Wl,--gc-sections", "driver.o", obj, "-o", "oracle-" + cc)
    for name, library in (("parent", parent), ("candidate", candidate)):
        run("gcc", "-Wl,--gc-sections", "driver.o", library, *LIBS, "-o", name)
        run("gcc", "-Wl,--gc-sections", "-DRUSTBOX_IPROUTE2_ENTRY=rustbox_iproute2_ip_main",
            ROOT / "bridges/iproute2_program_main.c", library, *LIBS, "-o", name + "-ip")
    local, vendor = Path("/etc/iproute2"), Path("/usr/share/iproute2")
    if not all(os.path.ismount(p) and not any(p.iterdir()) for p in (local, vendor)):
        raise ValueError("expected isolated empty configuration mounts")
    for p in (local, vendor):
        (p / "rt_protos.d").mkdir()
    profiles = []
    for profile in ("empty", "vendor", "local", "malformed"):
        if profile == "vendor":
            (vendor / "rt_protos").write_bytes(b"0 vendor\n17 duplicate\n255 raw-\xff\n")
            (vendor / "rt_protos.d/common.conf").write_bytes(b"201 vendor-overlay\n")
            (vendor / "rt_protos.d/unique.conf").write_bytes(b"202 vendor-only\n")
        if profile == "local":
            (local / "rt_protos").write_bytes(b"0 local\n33 duplicate\n255 raw-\xff\n")
            (local / "rt_protos.d/common.conf").write_bytes(b"201 local-overlay\n")
        if profile == "malformed":
            (local / "rt_protos").write_bytes(b"100 accepted\ninvalid-line\n0 ignored\n")
        expected = capture(["./oracle-gcc"])
        lines = expected[1].splitlines()
        if (expected[0] != 0 or b"first unspec" not in lines or bool(expected[2]) != (profile == "malformed")
                or sum(l.startswith(b"F ") for l in lines) != 5167 or sum(l.startswith(b"R ") for l in lines) != 298):
            raise ValueError(("unexpected canonical coverage", profile, expected[2]))
        if profile != "empty":
            label = b"vendor-overlay" if profile == "vendor" else b"local-overlay"
            if not any(l.endswith(b" " + label) for l in lines) or not any(l.endswith(b" vendor-only") for l in lines):
                raise ValueError("canonical probe missed a directory override")
        for cmd in (["./oracle-clang-18"], ["./parent"], ["./candidate"],
                    ["valgrind", "--error-exitcode=91", "--leak-check=no", "--log-file=memcheck.log", "./candidate"]):
            actual = capture(cmd)
            if actual != expected:
                mismatch = next(((a, b) for a, b in zip(lines, actual[1].splitlines()) if a != b), None)
                raise ValueError((profile, cmd, actual[0], actual[2], mismatch))
        if "ERROR SUMMARY: 0 errors" not in Path("memcheck.log").read_text():
            raise ValueError("routing protocol Memcheck failed")
        statuses = []
        for query in ("kernel", "static", "bgp", "local", "vendor", "vendor-only", "local-overlay", "255", "256", "unknown"):
            argv = ["ip", "-4", "route", "show", "protocol", query]
            output = capture(argv, executable="/rustbox-iproute2/programs-gcc/ip")
            for command in ("/rustbox-iproute2/programs-clang-18/ip", "./parent-ip", "./candidate-ip"):
                if capture(argv, executable=command) != output:
                    raise ValueError((profile, query, command))
            statuses.append(output[0])
        if not 0 < statuses.count(0) < len(statuses):
            raise ValueError("expected accepted and rejected read-only route filters")
        profiles.append(dict(profile=profile, forward=5167, reverse=298, public_ip_commands=len(statuses),
                             public_successes=statuses.count(0), stdout_sha256=sha256(expected[1]).hexdigest(),
                             stderr_sha256=sha256(expected[2]).hexdigest()))
    return dict(row, profiles=profiles, memcheck_runs=len(profiles), canonical_source_sha256=digest(source),
                oracle_compilers=["gcc", "clang-18"], lookup_driver_sha256=digest(DRIVER))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("pilot", type=Path)
    p.add_argument("link", type=Path)
    p.add_argument("--mounted", action="store_true")
    a = p.parse_args()
    if a.mounted:
        print(json.dumps(compare(a.pilot, a.link), indent=2, sort_keys=True))
    else:
        mounted_pilot = Path("/work") / a.pilot.resolve().relative_to(ROOT)
        mounted_link = Path("/work") / a.link.resolve().relative_to(ROOT)
        subprocess.run([
            "docker", "run", "--rm", "--network", "none", "--platform", "linux/amd64",
            "-v", f"{ROOT}:/work:ro", "-v", "rustbox-iproute2-7.3.0:/rustbox-iproute2:ro",
            "--tmpfs", "/etc/iproute2", "--tmpfs", "/usr/share/iproute2", "-w", "/tmp",
            "rustbox-e2fsprogs:2026-11-24", "python3", "-B", "/work/scripts/test_routing_protocol_pilot.py",
            mounted_pilot, mounted_link, "--mounted",
        ], check=True)
