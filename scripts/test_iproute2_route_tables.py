#!/usr/bin/env python3
"""Exercise the canonical route-table reader, owned Rust buckets and public ip filters on Linux."""
# SPDX-License-Identifier: GPL-2.0-or-later
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import subprocess

from build_iproute2_route_tables import CANONICAL, HELPER
from check_cargo_private_inlines import ROOT, digest
from test_iproute2_route_names import SOURCE, capture, run
from test_routing_protocol_pilot import LIBS

TEST = ROOT / "tests/iproute2-route-tables"
PROFILES = ("empty", "vendor", "local", "malformed", "overlay", "dangling", "directory")
QUERIES = ("main", "default", "local", "vendor", b"raw-\xff", "dup", "shadow", "missing", "4294967295")


def configure(profile, local, vendor):
    for root in (local, vendor):
        for child in root.iterdir():
            if child.is_dir() and not child.is_symlink():
                shutil.rmtree(child)
            else:
                child.unlink()
    if profile == "empty":
        return
    records = b"1 dup\n257 renamed\n257 dup\n2 dup\n255 raw-\xff\n2147483647 max\n-2 ignored\n"
    (vendor / "rt_tables").write_bytes(b"254 vendor\n" + records)
    if profile == "local":
        (local / "rt_tables").write_bytes(b"254 local\n" + records)
    if profile == "directory":
        (local / "rt_tables").mkdir()
    if profile == "malformed":
        (local / "rt_tables").write_bytes(b"254 part\nbad line\n255 after\n")
    if profile in ("overlay", "dangling"):
        vd, ld = vendor / "rt_tables.d", local / "rt_tables.d"
        vd.mkdir()
        ld.mkdir()
        (vd / "over.conf").write_bytes(b"254 shadow\n")
        (vd / "other.conf").write_bytes(b"700 extra\n")
        (vd / ".hidden.conf").write_bytes(b"254 hidden\n")
        (ld / "ignore.CONF").write_bytes(b"254 upper\n")
        if profile == "dangling":
            (ld / "over.conf").symlink_to("absent")
        else:
            (ld / "over.conf").write_bytes(b"254 last\n255 raw-\xff\n257 dup\n1 renamed\n")


def compare(link, pilot):
    if digest(CANONICAL) != "c7a7fbcfc2995b82fe50b8afd839311e45126e1d3dc135b732988c158f7ec77e":
        raise ValueError("unexpected canonical route table source")
    run("gcc", "-O2", "-Wall", "-Wextra", "-Werror", "-I" + str(SOURCE / "include"), "-c", TEST / "lookups.c", "-o", "driver.o")
    parser = ROOT / "tests/iproute2-group-names/reader.c"
    for cc in ("gcc", "clang-18"):
        db = json.loads((ROOT / f"work/analysis/iproute2-7.3.0/oracle/{cc}-compile-commands.json").read_bytes())
        args, = [x["arguments"] for x in db if x["file"].endswith("/lib/rt_names.c")]
        args[args.index("-o") + 1] = f"/tmp/{cc}.o"
        run(*args, "-ffunction-sections", "-fdata-sections", cwd=SOURCE / "lib")
        run(cc, "-Wl,--gc-sections", "driver.o", cc + ".o", "-o", "oracle-" + cc)
        if cc == "gcc" and not pilot:
            args[-1] = str(parser)
            args[args.index("-o") + 1] = "/tmp/parser.o"
            run(*args, "-I" + str(SOURCE / "lib"), "-Drtnl_rttable_n2a=original_table_forward",
                "-Drtnl_rttable_a2n=original_table_reverse", "-ffunction-sections", "-fdata-sections", cwd=SOURCE / "lib")
    row, public, oracles = {}, False, {}
    programs = ["./oracle-clang-18", "./candidate"]
    if pilot:
        parent = json.loads(link.read_bytes())
        row = json.loads((pilot / "pilot.json").read_bytes())
        key = Path(row["archive"])
        if (row["control_binary_sha256"] != parent["binary"]["sha256"] or row["control_sha256"] != parent["source_library_sha256"][str(key)]
                or digest(ROOT / key) != row["control_sha256"] or digest(pilot / key.name) != row["candidate_sha256"]
                or row["helper_sha256"] != digest(HELPER) or row["canonical_sha256"] != digest(CANONICAL)):
            raise ValueError("archive or compiler inputs changed")
        public = key.name == "libip_audit.a"
        programs.append("./control")
        for name, library in (("control", ROOT / key), ("candidate", pilot / key.name)):
            run("gcc", "-Wl,--gc-sections", "driver.o", library, *LIBS, "-o", name)
            if public:
                run("gcc", "-Wl,--gc-sections", "-DRUSTBOX_IPROUTE2_ENTRY=rustbox_iproute2_ip_main",
                    ROOT / "bridges/iproute2_program_main.c", library, *LIBS, "-o", name + "-ip")
        if public:
            baseline = json.loads((ROOT / "evidence/iproute2-routing-protocol-multicall.json").read_bytes())["canonical"]
            for cc in ("gcc", "clang-18"):
                oracles[cc] = digest(Path(f"/rustbox-iproute2/programs-{cc}/ip"))
                if oracles[cc] != baseline[cc]["canonical_sha256"]["ip"]:
                    raise ValueError("canonical ip changed")
    else:
        import tomllib
        crate = ROOT / "work/analysis/iproute2-7.3.0/program-translations/ip/ip-final"
        channel = tomllib.loads((crate / "rust-toolchain.toml").read_text())["toolchain"]["channel"]
        dep, = [p["version"] for p in tomllib.loads((crate / "Cargo.lock").read_text())["package"] if p["name"] == "libc"]
        Path("Cargo.toml").write_text(f'[package]\nname="route_tables"\nversion="0.0.0"\nedition="2021"\n'
            f'[lib]\ncrate-type=["staticlib"]\npath="{TEST / "standalone.rs"}"\n[dependencies]\nlibc="={dep}"\n')
        run("cargo", "+" + channel, "build", "--offline", "--release")
        run("gcc", "-Wl,--gc-sections", "driver.o", "target/release/libroute_tables.a", "parser.o", *LIBS, "-o", "candidate")

    local, vendor = Path("/etc/iproute2"), Path("/usr/share/iproute2")
    if not all(os.path.ismount(root) and not list(root.iterdir()) for root in (local, vendor)):
        raise ValueError("expected two empty private configuration mounts")
    profiles = []
    first_names = dict(empty=b"main", vendor=b"vendor", local=b"local", malformed=b"part",
                       overlay=b"last", dangling=b"vendor", directory=b"main")
    for profile in PROFILES:
        configure(profile, local, vendor)
        observed = {}
        for first in ("name", "numeric", "reverse"):
            expected = capture(["./oracle-gcc", first])
            lines = expected[1].splitlines()
            forwards = sum(x.startswith(b"F ") for x in lines)
            reverses = sum(x.startswith(b"R ") for x in lines)
            if (expected[0] or bool(expected[2]) != (profile == "malformed") or forwards != 8214 + (first == "numeric")
                    or reverses != 35 + (first == "reverse") or b"retained " + first_names[profile] + b" 1" not in lines):
                raise ValueError((profile, first, forwards, reverses, lines[-1:], expected[2]))
            commands = [[cmd, first] for cmd in programs]
            if first == "name":
                commands.append(["valgrind", "--error-exitcode=91", "--leak-check=no", "--log-file=memcheck.log", "./candidate", first])
            for cmd in commands:
                actual = capture(cmd, timeout=300)
                if actual != expected:
                    mismatch = next(((a,b) for a,b in zip(lines, actual[1].splitlines()) if a != b), None)
                    raise ValueError((profile, cmd, actual[0], actual[2], mismatch))
            if first == "name" and "ERROR SUMMARY: 0 errors" not in Path("memcheck.log").read_text():
                raise ValueError("route-table memory check failed")
            observed[first] = dict(forward=forwards, reverse=reverses, stdout_sha256=sha256(expected[1]).hexdigest(),
                                   stderr_sha256=sha256(expected[2]).hexdigest())
        statuses = []
        for query in QUERIES if public else ():
            args = ["ip", "-4", "route", "show", "table", query]
            expected = capture(args, executable="/rustbox-iproute2/programs-gcc/ip")
            for executable in ("/rustbox-iproute2/programs-clang-18/ip", "./control-ip", "./candidate-ip"):
                if capture(args, executable=executable) != expected:
                    raise ValueError((profile, query, executable, "route table filter differs"))
            statuses.append(expected[0])
        if public and not 0 < statuses.count(0) < len(statuses):
            raise ValueError("expected accepted and rejected table filters")
        profiles.append(dict(profile=profile, entry_sequences=observed, public_statuses=statuses))
    return dict(row, profiles=profiles, memcheck_runs=len(profiles), oracle_compilers=["gcc", "clang-18"],
                public_oracle_sha256=oracles, canonical_sha256=digest(CANONICAL), helper_sha256=digest(HELPER),
                driver_sha256=digest(TEST / "lookups.c"))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--link", type=Path)
    p.add_argument("--pilot", type=Path)
    p.add_argument("--mounted", action="store_true")
    args = p.parse_args()
    if bool(args.link) != bool(args.pilot):
        p.error("use --link with --pilot")
    if args.mounted:
        print(json.dumps(compare(args.link, args.pilot), indent=2, sort_keys=True))
    else:
        arguments = [] if not args.pilot else [flag for name, value in (("--link", args.link), ("--pilot", args.pilot))
                                               for flag in (name, Path("/work") / value.resolve().relative_to(ROOT))]
        subprocess.run(["docker", "run", "--rm", "--network", "none", "--platform", "linux/amd64",
            "--tmpfs", "/etc/iproute2", "--tmpfs", "/usr/share/iproute2", "-v", f"{ROOT}:/work:ro",
            "-v", "rustbox-pointer-cargo-registry:/root/.cargo/registry:ro", "-v", "rustbox-iproute2-7.3.0:/rustbox-iproute2:ro",
            "-w", "/tmp", "rustbox-e2fsprogs:2026-11-24", "python3", "-B", "/work/scripts/test_iproute2_route_tables.py",
            "--mounted", *arguments], check=True)
