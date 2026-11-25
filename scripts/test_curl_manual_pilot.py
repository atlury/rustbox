#!/usr/bin/env python3
"""Compare the packed curl manual and all advertised option-help spellings with canonical curl."""
# SPDX-License-Identifier: curl
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import subprocess

from check_cargo_private_inlines import ROOT, LINK_REPORT, digest

BASE = ROOT / "work/analysis/curl-8.23.0"


def compare(linked=False):
    pilot = Path("/pilot")
    release = json.loads(Path("/parent.json").read_bytes())
    binary = Path("/rustbox-coreutils/canonical-clang-no-security-compdb/src/rustbox")
    if linked:
        from curl_manual_archive import candidate_path, parent_view
        parent = parent_view(release)
        report = release["curl_manual"]["pilot"]
        candidate = ROOT / candidate_path(report)
        if (digest(binary) != release["binary"]["sha256"]
                or release["source_library_sha256"].get(str(candidate_path(report))) != report["candidate_sha256"]):
            raise ValueError("unexpected curl multicall or selected candidate")
    else:
        from curl_manual_archive import pilot_parent_view
        parent = pilot_parent_view(release)
        report = json.loads((pilot / "pilot.json").read_bytes())
        candidate = pilot / Path(report["archive"]).name
        if report["control_binary_sha256"] != parent["binary"]["sha256"]:
            raise ValueError("unexpected curl pilot control release")
    key = report["archive"]
    archive = ROOT / key
    if (parent["source_library_sha256"].get(key) != report["control_sha256"]
            or digest(archive) != report["control_sha256"] or digest(candidate) != report["candidate_sha256"]):
        raise ValueError("curl archive hashes differ from the selected control and pilot")
    sizes = {}
    for name, library in (("parent", archive), ("candidate", candidate)):
        subprocess.run(["clang-18", "-O2", "-g", "-fno-omit-frame-pointer", "-ffunction-sections",
                        "-fdata-sections", "-Wl,--gc-sections", "-o", name,
                        ROOT / "bridges/curl_main.c", BASE / "hybrid-artifacts/c-residue/mprintf.o",
                        library, "-ldl", "-lpthread", "-lm", "-lrt"], check=True)
        subprocess.run(["strip", "--strip-all", "-o", name + ".stripped", name], check=True)
        sizes[name] = Path(name + ".stripped").stat().st_size

    gcc = BASE / "oracle/curl-gcc"
    clang = BASE / "oracle/curl-clang"
    oracles = json.loads((ROOT / "evidence/curl-8.23.0-oracle.json").read_bytes())["binaries"]
    if digest(gcc) != oracles["gcc"]["sha256"] or digest(clang) != oracles["clang"]["sha256"]:
        raise ValueError("canonical curl executables differ from the recorded upstream builds")

    def run(exe, args, dispatch=False):
        argv = ["rustbox", "curl"] if dispatch else ["curl"]
        result = subprocess.run([*argv, "-q", *args], executable=exe, stdin=subprocess.DEVNULL,
                                capture_output=True, timeout=40)
        return result.returncode, result.stdout, result.stderr

    rc, advertised, err = run(gcc, ["--help", "all"])
    if rc or err:
        raise ValueError("canonical curl did not list its options")
    names = []
    option = re.compile(rb"^\s+(?:(-\S),\s+)?(--[a-z0-9][a-z0-9.-]*)(?=\s|$)")
    for entry in advertised.splitlines():
        match = option.match(entry)
        if not match:
            raise ValueError(("unrecognized advertised help entry", entry))
        names.append(match.groups())
    long_names = sorted({long.decode() for _, long in names})
    short_names = sorted({short.decode() for short, _ in names if short})
    if len(long_names) < 250 or len(short_names) < 40:
        raise ValueError("unexpected canonical option-help inventory")
    cases = [["--manual"], ["-M"], ["--help"], ["--help", "all"], ["--help", "category"],
             ["--help", "--no-such-option"], ["--help", "--no-output"], ["--help", b"--\xff"]]
    cases.extend(["--help", name] for name in long_names)
    cases.extend(["-h", name] for name in short_names)
    alternate = {("--" + name[5:] if name.startswith("--no-") else "--no-" + name[2:])
                 for name in long_names}
    cases.extend(["--help", name] for name in sorted(alternate - set(long_names))
                 if ["--help", name] not in cases)
    fingerprint = sha256()
    full = None
    public_sections = 0
    for args in cases:
        expected = run(gcc, args)
        for exe in (clang, Path("/tmp/parent"), Path("/tmp/candidate")):
            if run(exe, args) != expected:
                raise ValueError(("manual output differs", exe, args))
        if linked and (run(binary, args) != expected or run(binary, args, dispatch=True) != expected):
            raise ValueError(("linked curl manual output differs", args))
        if args == ["--manual"]:
            full = expected[1]
            # Hash of the 5,704 canonical C literals with one puts newline per record.
            if expected[0] or expected[2] or sha256(full).hexdigest() != "36b86ddf4660e65c4cbcb2ada287c390a8c07abdc66a0cb47c53b033941c3ce7":
                raise ValueError("expected the full built-in manual")
        if args == ["-M"] and expected[1] != full:
            raise ValueError("short manual option differs")
        if len(args) == 2 and args[1] in long_names and expected[1].strip():
            public_sections += 1
        for part in [*(os.fsencode(arg) for arg in args), str(expected[0]).encode(), *expected[1:]]:
            fingerprint.update(len(part).to_bytes(8, "big"))
            fingerprint.update(part)
    if public_sections < 250:
        raise ValueError("option-specific help did not return enough advertised sections")
    memory_cases = [["--manual"], ["--help", long_names[0]], ["--help", long_names[len(long_names)//2]],
                    ["--help", long_names[-1]], ["--help", "--no-such-option"]]
    for args in memory_cases:
        result = subprocess.run(["valgrind", "--error-exitcode=91", "--leak-check=no", "--log-file=/tmp/memcheck",
                                 "/tmp/candidate", "-q", *args], stdin=subprocess.DEVNULL, capture_output=True, timeout=120)
        if ((result.returncode, result.stdout, result.stderr) != run(gcc, args)
                or "ERROR SUMMARY: 0 errors" not in Path("/tmp/memcheck").read_text()):
            raise ValueError(("Memcheck or output mismatch", args))

    def failed_output(exe, sink, dispatch=False):
        if sink == "pipe":
            reader, writer = os.pipe()
            os.close(reader)
            target = os.fdopen(writer, "wb")
        else:
            target = open("/dev/full", "wb")
        with target:
            argv = ["rustbox", "curl"] if dispatch else ["curl"]
            result = subprocess.run([*argv, "-q", "--manual"], executable=exe, stdout=target,
                                    stdin=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=40)
        return result.returncode, result.stderr

    failures = {}
    for sink in ("pipe", "full"):
        observed = failed_output(gcc, sink)
        for exe in (clang, Path("/tmp/parent"), Path("/tmp/candidate")):
            if failed_output(exe, sink) != observed:
                raise ValueError(("error writing the manual differs", sink, exe))
        if linked and (failed_output(binary, sink) != observed or failed_output(binary, sink, dispatch=True) != observed):
            raise ValueError(("linked manual write failure differs", sink))
        failures[sink] = dict(status=observed[0], stderr_sha256=sha256(observed[1]).hexdigest())
    print(json.dumps(dict(report, canonical_gcc_sha256=digest(gcc), canonical_clang_sha256=digest(clang),
                          manual_bytes=len(full), manual_sha256=sha256(full).hexdigest(),
                          public_cases=len(cases), advertised_long=len(long_names), advertised_short=len(short_names),
                          option_sections=public_sections, memcheck_runs=len(memory_cases), write_errors=failures,
                          output_sha256=fingerprint.hexdigest(), standalone_stripped_bytes=sizes,
                          **({"multicall_sha256": digest(binary)} if linked else {})), indent=2, sort_keys=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pilot", type=Path, nargs="?")
    parser.add_argument("--link", type=Path, default=LINK_REPORT)
    parser.add_argument("--linked", action="store_true", help="exercise both multicall dispatch forms")
    parser.add_argument("--mounted", action="store_true")
    args = parser.parse_args()
    if args.mounted:
        compare(args.linked)
    elif args.pilot or args.linked:
        pilot = args.pilot or ROOT / "scripts"
        subprocess.run(["docker", "run", "--rm", "--network", "none", "--platform", "linux/amd64",
                        "-v", f"{ROOT}:/work:ro", "-v", f"{pilot.resolve(strict=True)}:/pilot:ro",
                        "-v", f"{args.link.resolve(strict=True)}:/parent.json:ro", "-w", "/tmp",
                        *(["-v", "rustbox-coreutils-9.12:/rustbox-coreutils:ro"] if args.linked else []),
                        "-e", "LC_ALL=C", "-e", "TZ=UTC", "rustbox-e2fsprogs:2026-11-24",
                        "python3", "-B", "/work/scripts/test_curl_manual_pilot.py", "--mounted",
                        *(["--linked"] if args.linked else [])], check=True)
    else:
        parser.error("supply the curl manual pilot directory")
