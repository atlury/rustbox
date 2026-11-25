#!/usr/bin/env python3
"""Compare Less's message API, saved strings and repeated overrides in both canonical link builds."""
# SPDX-License-Identifier: 0BSD
import argparse
from hashlib import sha256
import json
from pathlib import Path
import shlex
import subprocess
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from check_cargo_private_inlines import digest

SOURCE = ROOT / "work/upstream/less-710"
DRIVER = Path(__file__).with_name("catalog.c")


def run(link_file, pilot, work):
    link = json.loads(link_file.read_bytes())
    inputs = {name: digest(SOURCE / name) for name in ("lmsg.c", "lessmsg.inc", "main.c")}
    refs = json.loads((ROOT / "evidence/less-710-oracle.json").read_bytes())
    programs = {}
    for cc in ("gcc", "clang"):
        build = Path("/rustbox-less") / ("oracle-" + cc)
        oracle = ROOT / "work/analysis/less-710/oracle" / cc / "less"
        if digest(build / "less") != refs["binaries"][cc]["less"]["sha256"] or digest(oracle) != digest(build / "less"):
            raise ValueError("installed canonical Less differs")
        target = work / cc
        cmd, = subprocess.check_output(["make", "-n", "-W", "lmsg.o", "less"], cwd=build, text=True).strip().splitlines()
        args = shlex.split(cmd)
        if args[1:3] != ["-o", "less"] or args.count("lmsg.o") != 1 or args.count("main.o") != 1:
            raise ValueError("unexpected canonical Less link command")
        subprocess.run([args[0], "-Wl,--wrap=main", "-I" + str(SOURCE), DRIVER, "-o", target, *args[3:]], cwd=build, check=True)
        programs[cc] = target
    key, = [k for k in link["source_library_sha256"] if k.endswith("/libless_710_normalized_audit.a")]
    archive = ROOT / key
    if digest(archive) != link["source_library_sha256"][key]:
        raise ValueError("Less archive differs from release")
    libraries = {"parent": archive}
    if pilot:
        row = json.loads((pilot / "pilot.json").read_bytes())
        candidate = pilot / archive.name
        if (row["archive"] != key or row["candidate_sha256"] != digest(candidate) or row["control_sha256"] != digest(archive)
                or row["control_binary_sha256"] != link["binary"]["sha256"]):
            raise ValueError("unexpected Less candidate archive")
        libraries["candidate"] = candidate
    for name, library in libraries.items():
        target = work / name
        subprocess.run(["clang-18", "-Wl,--wrap=main,--gc-sections", "-I" + str(SOURCE), DRIVER, library,
                        "-ltinfo", "-ldl", "-lm", "-lpthread", "-o", target], check=True)
        programs[name] = target
    baseline = None
    invalid_result = None
    for name, target in programs.items():
        run = subprocess.run([target], cwd=work, capture_output=True, timeout=60)
        if (run.returncode or run.stderr or not run.stdout.endswith(b"count 331\n")
                or len(run.stdout.splitlines()) != 663 or baseline is not None and run.stdout != baseline):
            raise ValueError((name, run.returncode, run.stderr[:200], run.stdout[-80:]))
        baseline = run.stdout
        invalid = subprocess.run([target, "invalid"], cwd=work, capture_output=True, timeout=30)
        observation = (invalid.stdout, invalid.stderr)
        if (invalid.returncode or invalid.stdout.splitlines() != [b"rejected 0", b"rejected 332", b"rejected 4294967295"]
                or invalid_result is not None and observation != invalid_result):
            raise ValueError((name, "invalid message", invalid.returncode, observation))
        invalid_result = observation
    current = programs["candidate" if pilot else "parent"]
    log = work / "memcheck.log"
    run = subprocess.run(["valgrind", "--error-exitcode=99", "--leak-check=no", f"--log-file={log}", current], cwd=work,
                         capture_output=True, timeout=150, check=True)
    if run.stdout != baseline or run.stderr or "ERROR SUMMARY: 0 errors" not in log.read_text():
        raise ValueError("Less catalog memory check differs")
    public = {}
    if pilot:
        directory = work / "cli"
        directory.mkdir()
        subprocess.run(["clang-18", "-O2", "-Wl,--gc-sections", ROOT / "bridges/less_main.c", libraries["candidate"],
                        "-ltinfo", "-ldl", "-lm", "-lpthread", "-o", directory / "less"], check=True)
        (directory / "lessecho").symlink_to("less")
        for cc in ("gcc", "clang"):
            report = directory / (cc + ".json")
            subprocess.run(["python3", ROOT / "tests/less-oracle-differential.py", "--gcc-directory",
                            ROOT / "work/analysis/less-710/oracle" / cc, "--clang-directory", directory,
                            "--output", report], stdout=subprocess.DEVNULL, check=True)
            checked = json.loads(report.read_bytes())
            if not checked["cases"] or checked["cases"] != checked["passed"]:
                raise ValueError("incomplete Less command suite")
            public[cc] = checked["passed"]
    return dict(canonical_sources=inputs, canonical_builds={cc: digest(ROOT / "work/analysis/less-710/oracle" / cc / "less")
                for cc in ("gcc", "clang")}, compiler_archive_sha256=digest(archive), public_messages=331, reload_observations=662,
                invalid_ids=3, unknown_symbol_followed_by_valid_override=True,
                invalid_stderr_sha256=sha256(invalid_result[1]).hexdigest(), help_with_embedded_nul=True, output_sha256=sha256(baseline).hexdigest(), driver_sha256=digest(DRIVER),
                **({"candidate_sha256": digest(libraries["candidate"]), "command_cases": public} if pilot else {}))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("link", type=Path)
    p.add_argument("pilot", type=Path, nargs="?")
    a = p.parse_args()
    with TemporaryDirectory() as tmp:
        print(json.dumps(run(a.link, a.pilot, Path(tmp)), sort_keys=True, indent=2))
