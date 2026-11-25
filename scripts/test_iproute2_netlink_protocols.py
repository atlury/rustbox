#!/usr/bin/env python3
"""Compare a complete ss pilot and its netlink name ABI with IPRoute2 7.3.0."""
# SPDX-License-Identifier: GPL-2.0-or-later
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path

from check_cargo_private_inlines import ROOT, LINK_REPORT, digest
from iproute2_route_name_archives import candidate_path, verified_records
from test_iproute2_route_names import SOURCE, capture, run

DRIVER = ROOT / "tests/iproute2-netlink-protocols/lookups.c"


def compare():
    pilot = Path("/pilot")
    row = json.loads((pilot / "pilot.json").read_bytes())
    link = json.loads(Path("/control-link.json").read_bytes())
    key = row["archive"]
    parent = verified_records(link, link["iproute2_route_names"])[key]
    control = ROOT / candidate_path(parent)
    candidate = pilot / Path(key).name
    if (candidate.name != "libss_audit.a" or digest(control) != row["control_sha256"]
            or row["control_sha256"] != parent["candidate_sha256"]
            or row["control_binary_sha256"] != link["binary"]["sha256"]
            or digest(candidate) != row["candidate_sha256"]):
        raise ValueError("unexpected ss control or candidate")
    canonical = SOURCE / "lib/rt_names.c"
    if digest(canonical) != "c7a7fbcfc2995b82fe50b8afd839311e45126e1d3dc135b732988c158f7ec77e":
        raise ValueError("canonical netlink protocol implementation changed")
    database = ROOT / "work/analysis/iproute2-7.3.0/oracle/gcc-compile-commands.json"
    args, = (r["arguments"] for r in json.loads(database.read_bytes()) if r["file"].endswith("/rt_names.c"))
    args[args.index("-o") + 1] = "/tmp/oracle.o"
    run(*args, "-ffunction-sections", "-fdata-sections", cwd=canonical.parent)
    run("gcc", "-O2", "-Wall", "-Wextra", "-Werror", "-I" + str(SOURCE / "include"), "-c", DRIVER, "-o", "driver.o")
    run("gcc", "-Wl,--gc-sections", "driver.o", "oracle.o", "-o", "oracle")
    libs = "-ltirpc -lbpf -lelf -lmnl -lcap -ldb -lxtables -ldl -lpthread -lm".split()
    for name, archive in (("parent", control), ("candidate", candidate)):
        run("gcc", "-Wl,--gc-sections", "driver.o", archive, *libs, "-o", name)
        run("clang-18", "-O2", "-Wl,--gc-sections", "-DRUSTBOX_IPROUTE2_ENTRY=rustbox_iproute2_ss_main",
            ROOT / "bridges/iproute2_program_main.c", archive, *libs, "-o", name + "-ss")

    local = Path("/etc/iproute2")
    vendor = Path("/usr/share/iproute2")
    if not all(os.path.ismount(p) and not list(p.iterdir()) for p in (local, vendor)):
        raise ValueError("expected empty private configuration mounts")
    fixture = Path("/tmp/netlink")
    fixture.write_text("sk Eth Pid Groups Rmem Wmem Dump Locks\n" +
                       "".join(f"0 {id} 0 0 0 0 0 1\n" for id in (0, 16, 17, 100, 255)))
    os.environ["PROC_NET_NETLINK"] = str(fixture)
    profiles = []
    for profile in ("empty", "vendor", "local", "malformed"):
        if profile in ("vendor", "local"):
            directory = vendor if profile == "vendor" else local
            (directory / "nl_protos").write_bytes(f"0 {profile}\n".encode() + b"17 duplicate\n100 duplicate\n255 raw-\xff\n")
        elif profile == "malformed":
            (local / "nl_protos").write_bytes(b"100 first\nmalformed\n0 ignored\n")
        expected = capture(["./oracle"])
        lines = expected[1].splitlines()
        first = profile.encode() if profile in ("vendor", "local") else b"rtnl"
        if (expected[0] or bool(expected[2]) != (profile == "malformed") or b"first " + first not in lines
                or b"retained " + first + b" 1" not in lines
                or sum(x.startswith(b"F ") for x in lines) != 5167
                or sum(x.startswith(b"R ") for x in lines) != 298):
            raise ValueError(("unexpected canonical ABI observations", profile, expected[0], expected[2], len(lines)))
        for cmd in (["./parent"], ["./candidate"], ["valgrind", "--leak-check=no", "--error-exitcode=91",
                                                     "--log-file=/tmp/memcheck.log", "./candidate"]):
            actual = capture(cmd)
            if actual != expected:
                raise ValueError((profile, cmd, actual[0], actual[2],
                                  next(((x, y) for x, y in zip(lines, actual[1].splitlines()) if x != y), None)))
        if "ERROR SUMMARY: 0 errors" not in Path("/tmp/memcheck.log").read_text():
            raise ValueError("Memcheck failed")
        options = ([], ["-n"], *(["src", name] for name in
                   ("rtnl", "vendor", "local", "duplicate", b"raw-\xff", "0", "17", "255", "256", "bogus")))
        statuses = []
        for option in options:
            argv = ["ss", "-H", "-a", "-f", "netlink", *option]
            exp = capture(argv, executable="/rustbox-iproute2/programs-gcc/ss")
            if not option and (len(exp[1].splitlines()) != 5 or first not in exp[1]):
                raise ValueError(("socket fixture was not exercised", profile, exp))
            for impl in ("./parent-ss", "./candidate-ss"):
                if capture(argv, executable=impl) != exp:
                    raise ValueError((profile, impl, argv, exp))
            statuses.append(exp[0])
        if not 0 < statuses.count(0) < len(statuses):
            raise ValueError("expected successful and rejected filters")
        profiles.append(dict(profile=profile, forward=5167, reverse=298, public_commands=len(statuses),
                             public_successes=statuses.count(0), stdout_sha256=sha256(expected[1]).hexdigest(),
                             stderr_sha256=sha256(expected[2]).hexdigest()))
    print(json.dumps(dict(row, profiles=profiles, canonical_sha256=digest(canonical),
                          driver_sha256=digest(DRIVER), memcheck_runs=len(profiles)), sort_keys=True, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mounted", action="store_true")
    parser.add_argument("--link", type=Path, default=LINK_REPORT)
    parser.add_argument("pilot", type=Path, nargs="?")
    args = parser.parse_args()
    if args.mounted:
        compare()
    elif args.pilot:
        run("docker", "run", "--rm", "--network", "none", "--platform", "linux/amd64",
            "--tmpfs", "/etc/iproute2", "--tmpfs", "/usr/share/iproute2", "-e", "LC_ALL=C", "-e", "TZ=UTC",
            "-v", f"{ROOT}:/work:ro", "-v", f"{args.pilot.resolve(strict=True)}:/pilot:ro",
            "-v", f"{args.link.resolve(strict=True)}:/control-link.json:ro",
            "-v", "rustbox-iproute2-7.3.0:/rustbox-iproute2:ro", "-w", "/tmp", "rustbox-e2fsprogs:2026-11-24",
            "python3", "-B", "/work/scripts/test_iproute2_netlink_protocols.py", "--mounted")
    else:
        parser.error("select a complete ss pilot directory")
