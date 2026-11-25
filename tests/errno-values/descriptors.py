#!/usr/bin/env python3
"""Compare compiled GNU gzip and grep gnulib descriptor and allocation paths at their C interfaces."""
# SPDX-License-Identifier: 0BSD
import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from check_cargo_private_inlines import digest


def run(name, link, pilot, work):
    release = json.loads(link.read_bytes())
    version, library = {"grep": ("grep-3.12", "libgreputils.a"), "gzip": ("gzip-1.14", "libgzip.a")}[name]
    pins = json.loads((ROOT / ("evidence/" + version + "-oracle.json")).read_bytes())
    key, = [k for k in release["source_library_sha256"] if Path(k).name.startswith("lib" + name + "_") and k.endswith(".a")]
    archives = {"parent": ROOT / key}
    if digest(archives["parent"]) != release["source_library_sha256"][key]:
        raise ValueError("release archive differs")
    if pilot:
        row = json.loads((pilot / "pilot.json").read_bytes())
        archives["candidate"] = pilot / Path(key).name
        if (row["archive"] != key or row["control_sha256"] != digest(archives["parent"])
                or row["control_binary_sha256"] != release["binary"]["sha256"] or row["candidate_sha256"] != digest(archives["candidate"])):
            raise ValueError("candidate archive differs")
    volume = Path("/rustbox-" + name)
    cli = {}
    for cc in ("gcc", "clang"):
        build = volume / ("oracle-" + cc)
        binary = ROOT / "work/analysis" / version / "oracle" / (name + "-" + cc)
        ref = pins["binaries"][cc] if name == "grep" else pins["installed_surface"]["artifacts"][cc][name]
        if digest(binary) != ref["sha256"] or digest(build / ("src/grep" if name == "grep" else "gzip")) != digest(binary):
            raise ValueError("canonical executable differs")
        cli[cc] = binary
        archives[cc] = build / "lib" / library
    flags = ["-ldl", "-lpthread", "-lm"]
    extra = [ROOT / "bridges/grep_abi.c", "-lpcre2-8"] if name == "grep" else [volume / "normalized-clang/lib/libgzip.a"]
    if name == "gzip" and release["source_library_sha256"][str(extra[0])] != digest(extra[0]):
        raise ValueError("gzip support archive differs from release")
    driver = Path(__file__).with_name("descriptors.c")
    answers = {}
    for build, archive in archives.items():
        exe = work / ("api-" + build)
        nm = subprocess.check_output(["nm", "-g", "--defined-only", archive], stderr=subprocess.DEVNULL)
        symbols = {p[-1] for line in nm.splitlines() if len(p := line.split()) == 3 and p[-2] == b"T"}
        if not {b"fd_safer", b"pipe_safer", b"rpl_reallocarray"} <= symbols:
            raise ValueError("tested entry points must come from the selected archive")
        deps = [] if build in cli else extra
        subprocess.run(["clang-18", "-O2", "-Wl,--gc-sections", driver, archive, *deps, *flags, "-o", exe], check=True)
        for checked in (False, True):
            log = work / "memcheck"
            prefix = ["valgrind", "--leak-check=full", "--error-exitcode=99", "--log-file=" + str(log)] if checked else []
            result = subprocess.run([*prefix, exe], stdin=subprocess.DEVNULL, capture_output=True, check=True, timeout=180)
            if (result.stderr or result.stdout != b"5 errno states, 15 fd_safer calls, 5 pipes, 5 allocation failures\n"
                    or checked and "ERROR SUMMARY: 0 errors" not in log.read_text()):
                raise ValueError((build, checked, result.stderr))
            answers[build + ("-memcheck" if checked else "")] = sha256(result.stdout).hexdigest()
    command = {}
    if pilot:
        exe = work / name
        subprocess.run(["clang-18", "-O2", "-Wl,--gc-sections", ROOT / ("bridges/" + name + "_main.c"),
                        archives["candidate"], *extra, *flags, "-o", exe], check=True)
        for cc, ref in cli.items():
            report = work / (cc + ".json")
            if name == "grep":
                args = ["--gcc", ref, "--clang", exe]
            else:
                directory = volume / ("install-" + cc) / "usr/bin"
                if digest(directory / name) != digest(ref):
                    raise ValueError("installed canonical gzip differs")
                args = ["--gcc-directory", directory, "--clang-directory", work, "--applets", "gzip"]
            subprocess.run(["python3", ROOT / ("tests/" + name + "-oracle-differential.py"), *args, "--output", report],
                           check=True, stdout=subprocess.DEVNULL)
            data = json.loads(report.read_bytes())
            if name == "grep" and data["gcc_clang_exact"]:
                command[cc] = data["comparisons"]
            elif name == "gzip" and data["cases"] == data["passed"]:
                command[cc] = data["cases"]
            if not command.get(cc):
                raise ValueError("incomplete public command comparisons")
    return dict(archive_sha256={n: digest(p) for n,p in archives.items()}, api_outputs=answers,
                driver_sha256=digest(driver), fd_calls_per_run=15, pipe_transfers_per_run=5, allocation_errors_per_run=5,
                **({"public_commands": command} if pilot else {}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", choices=("grep", "gzip"))
    parser.add_argument("link", type=Path)
    parser.add_argument("pilot", type=Path, nargs="?")
    a = parser.parse_args()
    with TemporaryDirectory() as tmp:
        print(json.dumps(run(a.package, a.link, a.pilot, Path(tmp)), indent=2, sort_keys=True))
