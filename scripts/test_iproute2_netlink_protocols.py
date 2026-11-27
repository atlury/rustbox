#!/usr/bin/env python3
"""Compare netlink protocol lookups and public ss behavior with IPRoute2 7.3.0."""
# SPDX-License-Identifier: GPL-2.0-or-later
import argparse
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys

from check_cargo_private_inlines import ROOT, LINK_REPORT, digest
from iproute2_route_name_archives import candidate_path, netlink_control_view, netlink_path, verified_records
from iproute2_route_name_archives import lookup_archive, lookup_records, routing_lookup_pair
from test_iproute2_route_names import SOURCE, capture, run

DRIVER = ROOT / "tests/iproute2-netlink-protocols/lookups.c"


def compare(linked_key=None):
    pilot = Path("/pilot")
    link = json.loads(Path("/control-link.json").read_bytes())
    binary = Path("/rustbox-coreutils/canonical-clang-no-security-compdb/src/rustbox")
    routing = linked_key and "iproute2_routing_protocols" in link
    if routing:
        row, control, candidate = routing_lookup_pair(link, linked_key)
        if digest(binary) != link["binary"]["sha256"]:
            raise ValueError("unexpected multicall executable")
    elif linked_key:
        row = link["iproute2_netlink_protocols"][linked_key]
        verified_records(link, link["iproute2_netlink_protocols"], netlink=True)
        candidate = ROOT / netlink_path(row)
        if digest(binary) != link["binary"]["sha256"] or link["source_library_sha256"][str(netlink_path(row))] != row["candidate_sha256"]:
            raise ValueError("unexpected multicall or linked netlink archive")
        control_link = netlink_control_view(link)
    else:
        control_link = netlink_control_view(link)
        row = json.loads((pilot / "pilot.json").read_bytes())
        candidate = pilot / Path(row["archive"]).name
    if not routing:
        key = row["archive"]
        parent = verified_records(link, link["iproute2_route_names"])[key]
        control = ROOT / candidate_path(parent)
        if (row["control_sha256"] != parent["candidate_sha256"]
                or row["control_binary_sha256"] != control_link["binary"]["sha256"]
                or control_link["source_library_sha256"].get(str(candidate_path(parent))) != row["control_sha256"]):
            raise ValueError("unexpected netlink control")
    public_ss = candidate.name == "libss_audit.a"
    if digest(control) != row["control_sha256"] or digest(candidate) != row["candidate_sha256"]:
        raise ValueError("unexpected netlink archive bytes")
    canonical = SOURCE / "lib/rt_names.c"
    header = SOURCE / "include/rt_names.h"
    if (digest(canonical) != "c7a7fbcfc2995b82fe50b8afd839311e45126e1d3dc135b732988c158f7ec77e"
            or digest(header) != "b8223569a65254ecd3ea34c0368b253e355f558c270e246fdb7c240823b29414"):
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
        if public_ss:
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
            actual = capture(cmd, timeout=240) if cmd[0] == "valgrind" else capture(cmd)
            if actual != expected:
                raise ValueError((profile, cmd, actual[0], actual[2],
                                  next(((x, y) for x, y in zip(lines, actual[1].splitlines()) if x != y), None)))
        if "ERROR SUMMARY: 0 errors" not in Path("/tmp/memcheck.log").read_text():
            raise ValueError("Memcheck failed")
        options = ([], ["-n"], *(["src", name] for name in
                   ("rtnl", "vendor", "local", "duplicate", b"raw-\xff", "0", "17", "255", "256", "bogus")))
        statuses = []
        for option in options if public_ss else ():
            argv = ["ss", "-H", "-a", "-f", "netlink", *option]
            exp = capture(argv, executable="/rustbox-iproute2/programs-gcc/ss")
            if not option and (len(exp[1].splitlines()) != 5 or first not in exp[1]):
                raise ValueError(("socket fixture was not exercised", profile, exp))
            for impl in ("./parent-ss", "./candidate-ss"):
                if capture(argv, executable=impl) != exp:
                    raise ValueError((profile, impl, argv, exp))
            if linked_key:
                for command in (argv, ["rustbox", *argv]):
                    if capture(command, executable=binary) != exp:
                        raise ValueError((profile, "linked ss", command, exp))
            statuses.append(exp[0])
        if public_ss and not 0 < statuses.count(0) < len(statuses):
            raise ValueError("expected successful and rejected filters")
        profiles.append(dict(profile=profile, forward=5167, reverse=298, public_commands=len(statuses),
                             public_successes=statuses.count(0), stdout_sha256=sha256(expected[1]).hexdigest(),
                             stderr_sha256=sha256(expected[2]).hexdigest()))
    print(json.dumps(dict(row, profiles=profiles, canonical_sha256=digest(canonical),
                          driver_sha256=digest(DRIVER), memcheck_runs=len(profiles),
                          **({"multicall_sha256": digest(binary)} if linked_key else {})), sort_keys=True, indent=2))


def qualify_archive(key, row, pilot, link_path, output, reference, multicall_hash=None):
    name = Path(key).stem.removeprefix("lib").removesuffix("_audit")
    target = output / (name + ".json")
    if digest(DRIVER) != reference["driver_sha256"] or digest(SOURCE / "lib/rt_names.c") != reference["canonical_sha256"]:
        raise ValueError("netlink oracle or comparison driver differs from the qualified pilot")
    if not target.exists() or multicall_hash is not None:
        select = ["--linked-key", key] if multicall_hash is not None else [pilot / name]
        data = subprocess.check_output([sys.executable, "-B", __file__, *select, "--link", link_path])
    else:
        data = target.read_bytes()
    result = json.loads(data)
    profiles = [dict(profile) for profile in reference["profiles"]]
    if name != "ss":
        for profile in profiles:
            profile.update(public_commands=0, public_successes=0)
    expected = dict(row, profiles=profiles, **{k: reference[k] for k in
                    ("driver_sha256", "canonical_sha256", "memcheck_runs")})
    archive = ROOT / lookup_archive(json.loads(link_path.read_bytes()), key) if multicall_hash is not None else pilot / name / Path(key).name
    if multicall_hash is not None:
        expected["multicall_sha256"] = multicall_hash
    if result != expected or digest(archive) != result["candidate_sha256"]:
        raise ValueError(f"{name} failed netlink protocol qualification")
    target.write_bytes(data)
    print(f"{name} passed", flush=True)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--linked-key", help=argparse.SUPPRESS)
    parser.add_argument("--linked", action="store_true", help="compare the selected release archives and multicall ss")
    parser.add_argument("--batch", type=Path, help="write per-engine comparisons to this directory")
    parser.add_argument("--jobs", type=int, default=3)
    parser.add_argument("--mounted", action="store_true")
    parser.add_argument("--link", type=Path, default=LINK_REPORT)
    parser.add_argument("pilot", type=Path, nargs="?")
    args = parser.parse_args()
    if args.mounted:
        compare(args.linked_key)
    elif args.batch and (args.pilot or args.linked):
        if args.jobs < 1:
            parser.error("--jobs must be positive")
        args.batch.mkdir(parents=True, exist_ok=True)
        link = json.loads(args.link.read_bytes())
        rows = lookup_records(link) if args.linked else json.loads((args.pilot / "archives.json").read_bytes())
        if not (args.linked and "iproute2_routing_protocols" in link):
            verified_records(link, rows, netlink=True)
            control_sha = netlink_control_view(link)["binary"]["sha256"]
            if any(row["control_binary_sha256"] != control_sha for row in rows.values()):
                raise ValueError("netlink protocol candidates refer to another parent release")
        reference = json.loads((ROOT / "evidence/iproute2-netlink-protocols-pilot.json").read_bytes())

        def check(key):
            return qualify_archive(key, rows[key], args.pilot, args.link, args.batch, reference,
                                   link["binary"]["sha256"] if args.linked else None)

        with ThreadPoolExecutor(max_workers=args.jobs) as pool:
            checked = dict(zip(sorted(rows), pool.map(check, sorted(rows))))
        (args.batch / "results.json").write_text(json.dumps(checked,
                                                            indent=2, sort_keys=True) + "\n")
    elif args.pilot or args.linked_key:
        pilot = args.pilot or ROOT / "scripts"
        run("docker", "run", "--rm", "--network", "none", "--platform", "linux/amd64",
            "--tmpfs", "/etc/iproute2", "--tmpfs", "/usr/share/iproute2", "-e", "LC_ALL=C", "-e", "TZ=UTC",
            "-v", f"{ROOT}:/work:ro", "-v", f"{pilot.resolve(strict=True)}:/pilot:ro",
            "-v", f"{args.link.resolve(strict=True)}:/control-link.json:ro",
            "-v", "rustbox-iproute2-7.3.0:/rustbox-iproute2:ro",
            *(["-v", "rustbox-coreutils-9.12:/rustbox-coreutils:ro"] if args.linked_key else []), "-w", "/tmp", "rustbox-e2fsprogs:2026-11-24",
            "python3", "-B", "/work/scripts/test_iproute2_netlink_protocols.py", "--mounted",
            *(["--linked-key", args.linked_key] if args.linked_key else []))
    else:
        parser.error("select a complete ss pilot directory")
