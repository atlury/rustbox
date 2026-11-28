#!/usr/bin/env python3
"""Compare IPRoute2 device-group lookup results, output buffers, errno and retained names on Linux."""
# SPDX-License-Identifier: GPL-2.0-or-later
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess

from build_group_names import CANONICAL, HELPER
from check_cargo_private_inlines import ROOT, digest
from test_iproute2_route_names import SOURCE, capture, run
from test_routing_protocol_pilot import LIBS

TEST = ROOT / "tests/iproute2-group-names"
PROFILES = ("empty", "vendor", "local", "corrupt", "directory")


def configure(profile, local, vendor):
    for file in (local, vendor):
        if file.is_dir():
            file.rmdir()
        elif file.exists():
            file.unlink()
    if profile == "empty":
        return
    records = (b"257 dup\n7 dup\n513 samebucket\n257 samebucket\n257 renamed\n1 dup\n"
               b"256 default\n2 raw-\xff\n-2 ignored\n2147483647 max\n")
    vendor.write_bytes(b"0 vendor\n" + records)
    if profile == "local":
        local.write_bytes(b"0 local\n" + records)
    if profile == "corrupt":
        local.write_bytes(b"512 first\ninvalid line\n0 ignored\n")
    if profile == "directory":
        local.mkdir()


def compare(link, pilot):
    if digest(CANONICAL) != "c7a7fbcfc2995b82fe50b8afd839311e45126e1d3dc135b732988c158f7ec77e":
        raise ValueError("unexpected canonical group-name input")
    run("gcc", "-O2", "-Wall", "-Wextra", "-Werror", "-I"+str(SOURCE/"include"), "-c", TEST/"lookups.c", "-o", "driver.o")
    for cc in ("gcc","clang-18"):
        db = json.loads((ROOT/f"work/analysis/iproute2-7.3.0/oracle/{cc}-compile-commands.json").read_bytes())
        args, = [r["arguments"] for r in db if r["file"].endswith("/rt_names.c")]
        args = list(args)
        args[args.index("-o")+1] = "/tmp/"+cc+".o"
        run(*args, "-ffunction-sections", "-fdata-sections", cwd=SOURCE/"lib")
        run(cc, "-Wl,--gc-sections","driver.o",cc+".o","-o","oracle-"+cc)
        if cc == "gcc" and not pilot:
            args[-1] = str(TEST/"reader.c")
            args[args.index("-o")+1] = "/tmp/parser.o"
            run(*args, "-I"+str(SOURCE/"lib"), "-Drtnl_group_a2n=original_group_a2n", "-Drtnl_group_n2a=original_group_n2a",
                "-ffunction-sections", "-fdata-sections", cwd=SOURCE/"lib")
    public_oracles = {}
    ip = False
    if pilot:
        parent = json.loads(link.read_bytes())
        row = json.loads((pilot/"pilot.json").read_bytes())
        key = row["archive"]
        if (parent["binary"]["sha256"] != row["control_binary_sha256"] or parent["source_library_sha256"][key] != row["control_sha256"]
            or digest(ROOT/key) != row["control_sha256"] or digest(pilot/Path(key).name) != row["candidate_sha256"] or digest(HELPER) != row["helper_sha256"]):
            raise ValueError("device-group archive or compiler input changed")
        ip = Path(key).name == "libip_audit.a"
        if ip:
            tested = json.loads((ROOT / "evidence/iproute2-routing-protocol-multicall.json").read_bytes())["canonical"]
            for cc in ("gcc", "clang-18"):
                checksum = digest(Path(f"/rustbox-iproute2/programs-{cc}/ip"))
                if checksum != tested[cc]["canonical_sha256"]["ip"]:
                    raise ValueError("canonical ip executable changed")
                public_oracles[cc] = checksum
        for name, archive in (("control",ROOT/key),("candidate",pilot/Path(key).name)):
            run("gcc","-Wl,--gc-sections","driver.o",archive,*LIBS,"-o",name)
            if ip:
                run("clang-18","-O2","-Wl,--gc-sections","-DRUSTBOX_IPROUTE2_ENTRY=rustbox_iproute2_ip_main",
                    ROOT/"bridges/iproute2_program_main.c",archive,*LIBS,"-o",name+"-ip")
        programs = ["./oracle-clang-18","./control","./candidate"]
    else:
        import tomllib
        config = ROOT / "work/analysis/iproute2-7.3.0/program-translations/ip/ip-final/rust-toolchain.toml"
        channel = tomllib.loads(config.read_text())["toolchain"]["channel"]
        run("rustc","+"+channel,"--crate-type","staticlib","--edition","2021","-C","opt-level=2",
            TEST/"standalone.rs","-o","helper.a")
        run("gcc","-Wl,--gc-sections","driver.o","helper.a","parser.o","-ldl","-lpthread","-lm","-o","candidate")
        programs = ["./oracle-clang-18","./candidate"]
    local, vendor = (Path(p) for p in ("/etc/iproute2","/usr/share/iproute2"))
    if not all(os.path.ismount(p) and not list(p.iterdir()) for p in (local,vendor)):
        raise ValueError("expected empty private configuration mounts")
    profiles = []
    for profile in PROFILES:
        configure(profile,local/"group",vendor/"group")
        expected = capture(["./oracle-gcc"])
        lines = expected[1].splitlines()
        forwards = sum(x.startswith(b"F ") for x in lines)
        reverses = sum(x.startswith(b"R ") for x in lines)
        if expected[0] or forwards != 6178 or reverses != 29 or bool(expected[2]) != (profile=="corrupt"):
            raise ValueError((profile,"unexpected canonical coverage",forwards,reverses,expected[2]))
        first_name = profile.encode() if profile in ("vendor", "local") else b"default"
        if not lines[0].startswith(b"first " + first_name + b" ") or lines[-1] != b"retained " + first_name + b" 1":
            raise ValueError((profile, "canonical group initialization or pointer lifetime changed"))
        if profile in ("vendor", "local"):
            if not all(any(line.startswith(prefix) for line in lines) for prefix in
                       (b"R dup 0 1 ", b"R samebucket 0 257 ", b"R default 0 256 ", b"R raw-\xff 0 2 ")):
                raise ValueError((profile, "canonical hash collisions or bucket ordering changed"))
        for program in programs:
            observed = capture([program])
            if observed != expected:
                mismatch = next(((a,b) for a,b in zip(lines,observed[1].splitlines()) if a != b), None)
                raise ValueError((profile,program,observed[0],observed[2],mismatch))
        checked = capture(["valgrind","--error-exitcode=91","--leak-check=no","--log-file=/tmp/memcheck.log","./candidate"],timeout=240)
        if checked != expected or "ERROR SUMMARY: 0 errors" not in Path("/tmp/memcheck.log").read_text():
            raise ValueError((profile,"Memcheck or program output differed"))
        statuses = []
        if ip:
            for name in ("0","local","vendor","default","dup","raw-ÿ".encode("latin1"),"0x101","missing","-1","4294967297"):
                argv = ["ip","link","show","group",name]
                canonical = capture(argv,executable="/rustbox-iproute2/programs-gcc/ip")
                for exe in ("/rustbox-iproute2/programs-clang-18/ip","./control-ip","./candidate-ip"):
                    if capture(argv,executable=exe) != canonical:
                        raise ValueError((profile, name, exe, "ip link group filter differs"))
                statuses.append(canonical[0])
            if not 0 < statuses.count(0) < len(statuses):
                raise ValueError("expected accepted and rejected canonical group filters")
        profiles.append(dict(profile=profile,forward=forwards,reverse=reverses,public_statuses=statuses,
                             stdout_sha256=sha256(expected[1]).hexdigest(),stderr_sha256=sha256(expected[2]).hexdigest()))
    result = dict(row) if pilot else {}
    return dict(result, profiles=profiles, memcheck_runs=len(profiles), canonical_sha256=digest(CANONICAL),
                helper_sha256=digest(HELPER), driver_sha256=digest(TEST/"lookups.c"),
                oracle_compilers=["gcc", "clang-18"], public_oracle_sha256=public_oracles)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--link", type=Path)
    p.add_argument("--pilot", type=Path)
    p.add_argument("--mounted", action="store_true")
    args = p.parse_args()
    if bool(args.link) != bool(args.pilot):
        p.error("the translated archive needs both --pilot and --link")
    if args.mounted:
        print(json.dumps(compare(args.link,args.pilot),indent=2,sort_keys=True))
    else:
        opts = [] if not args.pilot else ["--link",Path("/work")/args.link.resolve().relative_to(ROOT),"--pilot",Path("/work")/args.pilot.resolve().relative_to(ROOT)]
        run("docker","run","--rm","--network","none","--platform","linux/amd64","--tmpfs","/etc/iproute2","--tmpfs","/usr/share/iproute2",
            "-v",f"{ROOT}:/work:ro","-v","rustbox-iproute2-7.3.0:/rustbox-iproute2:ro","-w","/tmp","rustbox-e2fsprogs:2026-11-24",
            "python3","-B","/work/scripts/test_group_names.py","--mounted",*opts)
