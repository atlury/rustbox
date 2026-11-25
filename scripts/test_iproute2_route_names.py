#!/usr/bin/env python3
"""Compare the scope/realm candidate to the canonical IPRoute2 compiler input and complete linked parent."""
# SPDX-License-Identifier: GPL-2.0-or-later
import argparse
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import json
import os
import re
from pathlib import Path
import subprocess

from check_cargo_private_inlines import ROOT, LINK_REPORT, digest
from iproute2_address_protocol_archive import ARCHIVE, candidate_path, selected_records

HERE = Path(__file__).resolve()
SOURCE = ROOT / "work/upstream/iproute2-7.3.0"
DRIVER = ROOT / "tests/iproute2-route-names/lookups.c"


def run(*args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def capture(args, *, executable=None):
    result = subprocess.run(args, executable=executable, capture_output=True, timeout=60)
    return result.returncode, result.stdout, result.stderr


def compare(pilot, key, live=False):
    from iproute2_route_name_archives import build_control_view, candidate_path as route_path
    release = json.loads(Path("/control-link.json").read_bytes())
    binary = Path("/rustbox-coreutils/canonical-clang-no-security-compdb/src/rustbox")
    if live and "iproute2_netlink_protocols" in release:
        from iproute2_route_name_archives import netlink_path, netlink_control_view
        report = release["iproute2_netlink_protocols"][key]
        link = netlink_control_view(release)
        variant = ROOT / netlink_path(report)
        if digest(binary) != release["binary"]["sha256"]:
            raise ValueError("unexpected multicall executable")
    elif live:
        report = release["iproute2_route_names"][key]
        link = build_control_view(release)
        variant = ROOT / route_path(report)
        if digest(binary) != release["binary"]["sha256"]:
            raise ValueError("unexpected multicall executable")
    else:
        link = build_control_view(release)
        report = json.loads((pilot / "pilot.json").read_bytes())
        variant = pilot / Path(key).name
    parent = ROOT / (route_path(link["iproute2_route_names"][key]) if "iproute2_route_names" in link
                     else candidate_path(selected_records(link)[key]))
    if (report["archive"] != key or digest(parent) != report["control_sha256"]
            or link["source_library_sha256"][str(parent.relative_to(ROOT))] != report["control_sha256"]
            or report["control_binary_sha256"] != link["binary"]["sha256"]
            or digest(variant) != report["candidate_sha256"]):
        raise ValueError("unexpected scope/realm pilot or linked parent")
    oracle_sources = {key: digest(SOURCE / key) for key in ("lib/rt_names.c", "include/rt_names.h")}
    if list(oracle_sources.values()) != ["c7a7fbcfc2995b82fe50b8afd839311e45126e1d3dc135b732988c158f7ec77e",
                                         "b8223569a65254ecd3ea34c0368b253e355f558c270e246fdb7c240823b29414"]:
        raise ValueError("canonical IPRoute2 source changed")
    database = ROOT / "work/analysis/iproute2-7.3.0/oracle/gcc-compile-commands.json"
    args, = (row["arguments"] for row in json.loads(database.read_bytes()) if row["file"].endswith("/rt_names.c"))
    args[args.index("-o") + 1] = "/tmp/oracle.o"
    run(*args, "-ffunction-sections", "-fdata-sections", cwd=SOURCE / "lib")
    run("gcc", "-O2", "-Wall", "-Wextra", "-Werror", "-I" + str(SOURCE / "include"), "-c", DRIVER, "-o", "driver.o")
    run("gcc", "-Wl,--gc-sections", "driver.o", "oracle.o", "-o", "canonical")
    libs = "-ltirpc -lbpf -lelf -lmnl -lcap -ldb -lxtables -ldl -lpthread -lm".split()
    for name, archive in (("parent", parent), ("candidate", variant)):
        run("gcc", "-Wl,--gc-sections", "driver.o", archive, *libs, "-o", name)
        if key == str(ARCHIVE):
            run("clang-18", "-O2", "-Wl,--gc-sections", "-DRUSTBOX_IPROUTE2_ENTRY=rustbox_iproute2_ip_main",
                ROOT / "bridges/iproute2_program_main.c", archive, *libs, "-o", name + "-ip")
    local = Path("/etc/iproute2")
    vendor = Path("/usr/share/iproute2")
    if not all(os.path.ismount(p) and not list(p.iterdir()) for p in (local, vendor)):
        raise ValueError("expected empty private mounts")

    def symbols(path):
        lines = subprocess.check_output(["nm", "-g", "--defined-only", path], text=True, stderr=subprocess.DEVNULL)
        names = {fields[-1] for line in lines.splitlines() if len(fields := line.split()) >= 3
                 and fields[-2] in {"B", "C", "D", "G", "R", "S", "T"} and re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", fields[-1])
                 and not fields[-1].startswith("_R")}
        return names

    before, after = symbols(parent), symbols(variant)
    delta = {"added": sorted(after - before), "removed": sorted(before - after)}
    if any(not name.startswith("_ZN") for names in delta.values() for name in names):
        raise ValueError("strong C symbols changed")
    outputs = []
    public = []
    for profile in ("empty", "vendor", "local", "malformed"):
        for filename in ("rt_scopes", "rt_realms"):
            if profile == "vendor":
                (vendor / filename).write_bytes(b"0 vendor\n100 vendor-only\n45 duplicate\n20 duplicate\n255 raw-\xff\n")
            if profile == "local":
                (local / filename).write_bytes(b"0 local\n100 local-only\n55 duplicate\n15 duplicate\n255 raw-\xff\n")
            if profile == "malformed":
                (local / filename).write_bytes(b"100 first\nbad-line\n200 ignored\n")
        oracle = capture(["./canonical"])
        if oracle[0] or bool(oracle[2]) != (profile == "malformed"):
            raise ValueError(("unexpected canonical status or diagnostics", profile, oracle[0], oracle[2]))
        lines = oracle[1].splitlines()
        if (sum(line.startswith(b"F ") for line in lines) != 10332
                or sum(line.startswith(b"R ") for line in lines) != 180):
            raise ValueError("incomplete canonical lookup matrix")
        for t, builtin in enumerate((b"global", b"unknown")):
            prefix = str(t).encode() + b" "
            loaded = {"vendor": b"vendor", "local": b"local"}.get(profile, builtin)
            if (b"initial " + prefix + builtin not in lines
                    or b"loaded " + prefix + loaded + b" retained " + builtin + b" identical " + str(int(loaded == builtin)).encode() not in lines):
                raise ValueError(("canonical deferred loading", profile, t))
            if profile == "empty" and not any(line.startswith(b"R " + prefix + builtin + b" 0 256 ") for line in lines):
                raise ValueError("canonical lookup-order cache was not exercised")
        log = Path(f"/tmp/memcheck-{profile}.log")
        for command in (["./parent"], ["./candidate"], ["valgrind", "--error-exitcode=91", "--leak-check=no", f"--log-file={log}", "./candidate"]):
            actual = capture(command)
            if actual != oracle:
                differing = next(((a, b) for a, b in zip(lines, actual[1].splitlines()) if a != b), None)
                raise ValueError((profile, command, actual[0], actual[2], differing))
        if "ERROR SUMMARY: 0 errors" not in log.read_text():
            raise ValueError("Memcheck failed")
        outputs.append({"profile": profile, "lookup_rows": len(lines) - 4, "stdout_sha256": sha256(oracle[1]).hexdigest(),
                        "stderr_sha256": sha256(oracle[2]).hexdigest()})
        if key != str(ARCHIVE):
            continue
        filters = (["-j", "address", "show", "dev", "lo", "scope"], ["-j", "route", "show", "scope"],
                   ["-j", "route", "show", "realms"])
        for args in filters:
            for query in ("global", "unknown", "0", "local", "duplicate", b"raw-\xff", "256", "bad-value"):
                argv = ["ip", *args, query]
                expected = capture(argv, executable="/rustbox-iproute2/programs-gcc/ip")
                targets = [("./parent-ip", argv), ("./candidate-ip", argv)]
                if live:
                    targets.extend([(binary, argv), (binary, ["rustbox", *argv])])
                if any(capture(command, executable=exe) != expected for exe, command in targets):
                    raise ValueError(("public ip mismatch", profile, argv))
                public.append(expected[0])
    if key == str(ARCHIVE) and not (0 < public.count(0) < len(public)):
        raise ValueError("expected successful and rejected public commands")
    print(json.dumps(dict(report, profiles=outputs, public_commands=len(public), public_successes=public.count(0),
                          memcheck_runs=len(outputs), canonical_sources=oracle_sources,
                          driver_sha256=digest(DRIVER), strong_symbol_changes=delta,
                          **({"multicall_sha256": release["binary"]["sha256"]} if live else {})), sort_keys=True, indent=2))


def linux_comparison(pilot, key, link, output=None, *, live=False):
    cmd = ["docker", "run", "--rm", "--network", "none", "--platform", "linux/amd64",
           "--tmpfs", "/etc/iproute2", "--tmpfs", "/usr/share/iproute2", "-e", "LC_ALL=C", "-e", "TZ=UTC",
           "-v", f"{ROOT}:/work:ro", "-v", f"{pilot.resolve(strict=True)}:/pilot:ro",
           "-v", f"{link.resolve(strict=True)}:/control-link.json:ro",
           "-v", "rustbox-iproute2-7.3.0:/rustbox-iproute2:ro", "-w", "/tmp", "rustbox-e2fsprogs:2026-11-24",
           "python3", "-B", "/work/scripts/" + HERE.name, "/pilot", "--mounted", key]
    if live:
        position = cmd.index("-w")
        cmd[position:position] = ["-v", "rustbox-coreutils-9.12:/rustbox-coreutils:ro"]
        cmd.append("--linked")
    if output is None:
        run(*cmd)
    else:
        with output.open("w") as stream:
            run(*cmd, stdout=stream)
        return json.loads(output.read_bytes())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pilot", type=Path, nargs="?", default=ROOT, help="single ip candidate or batch build directory")
    parser.add_argument("--link", type=Path, default=LINK_REPORT, help="link report selecting the parent archives")
    parser.add_argument("--linked", action="store_true", help="exercise all selected scope/realm archives and the actual multicall")
    parser.add_argument("--batch", type=Path, help="new output directory for comparisons of all 18 engines")
    parser.add_argument("--jobs", type=int, default=3)
    parser.add_argument("--mounted", metavar="ARCHIVE", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.mounted:
        compare(args.pilot, args.mounted, args.linked)
    elif args.batch:
        release = json.loads(args.link.read_bytes())
        parents = selected_records(release)
        manifest = (release.get("iproute2_netlink_protocols", release["iproute2_route_names"]) if args.linked
                    else json.loads((args.pilot / "archives.json").read_bytes()))
        if len(parents) != 18 or parents.keys() != manifest.keys() or args.jobs < 1:
            parser.error("expected all linked IPRoute2 archives and a positive job count")
        args.batch.mkdir()
        def compare_one(key):
            name = Path(key).stem.removeprefix("lib").removesuffix("_audit")
            directory = args.pilot / name if not args.linked else HERE.parent
            data = linux_comparison(directory, key, args.link, args.batch / (name + ".json"), live=args.linked)
            if any(data[k] != v for k, v in manifest[key].items()):
                raise ValueError(f"{name} comparison used unexpected inputs")
            print(f"{name} passed", flush=True)
            return data
        with ThreadPoolExecutor(max_workers=args.jobs) as pool:
            rows = list(pool.map(compare_one, sorted(parents)))
        (args.batch / "results.json").write_text(json.dumps({r["archive"]: r for r in rows}, indent=2, sort_keys=True) + "\n")
    else:
        linux_comparison(args.pilot, str(ARCHIVE), args.link, live=args.linked)
