#!/usr/bin/env python3
"""Compare the checked errno archives for Shadow and GNU Findutils in their public programs."""
# SPDX-License-Identifier: 0BSD
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import shutil
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from check_cargo_private_inlines import digest


def shadow(archive, release, dest):
    pins = json.loads((ROOT / "evidence/shadow-4.20.4-oracle.json").read_bytes())
    exe = dest / "shadow"
    subprocess.run(["clang-18", "-O2", "-Wl,--gc-sections", ROOT / "bridges/shadow_main.c", archive,
                    "-lcrypt", "-ldl", "-lpthread", "-lm", "-lrt", "-o", exe], check=True)
    for name in pins["programs"]:
        (dest / name).symlink_to(exe)
    result = {}
    for cc, refs in pins["binaries"].items():
        directory = Path("/rustbox-shadow") / ("programs-gcc" if cc == "gcc" else "programs-clang-18")
        for name, ref in refs.items():
            if digest(directory / name) != ref["sha256"]:
                raise ValueError("canonical Shadow program differs")
        report = dest / (cc + ".json")
        subprocess.run(["python3", ROOT / "tests/shadow-oracle-differential.py", "--gcc-root", directory,
                        "--clang-root", dest, "--output", report], check=True, stdout=subprocess.DEVNULL)
        row = json.loads(report.read_bytes())
        if row["cases"] != row["passed"] or not row["stateful_cases"] or row["programs"] != len(pins["programs"]):
            raise ValueError("incomplete Shadow command or account fixture coverage")
        result[cc] = {k: row[k] for k in ("cases", "passed", "stateful_cases", "programs")}
    return result


def findutils(archive, release, dest):
    base = ROOT / "work/analysis/findutils-4.10.0"
    pins = json.loads((ROOT / "evidence/findutils-4.10.0-oracle.json").read_bytes())
    residues = sorted((base / "hybrid-artifacts/c-residue").glob("*.o"))
    if ([p.name for p in residues] != ["printf-args.o", "printf-parse.o", "vasnprintf.o"]
            or any(digest(p) != release["source_library_sha256"].get(str(p.relative_to(ROOT))) for p in residues)):
        raise ValueError("unexpected Findutils ABI helpers")
    paths = ("find/find", "xargs/xargs", "locate/locate", "locate/frcode", "locate/updatedb")
    for relative in paths[:-1]:
        target = dest / relative
        target.parent.mkdir(exist_ok=True)
        front = [ROOT / "bridges/findutils_main.c"]
        subprocess.run(["clang-18", "-O2", "-Wl,--gc-sections", "-DRUSTBOX_ENTRY=rustbox_" + target.name + "_main",
                        *front, *residues, archive, "-ldl", "-lpthread", "-lm", "-lrt", "-lutil", "-o", target], check=True)
    # At archive level the canonical shell uses the candidate find and frcode.
    # The integrated updatedb adapter also requires Rustbox's Coreutils dispatcher.
    updatedb = Path("/rustbox-findutils/oracle-clang/locate/updatedb")
    shutil.copy2(updatedb, dest / "locate/updatedb")
    result = {}
    for cc in ("gcc", "clang"):
        directory = Path("/rustbox-findutils") / ("oracle-" + cc)
        for relative in paths[:-1]:
            name = Path(relative).name
            installed = base / "oracle" / (cc + "-root/usr") / ("libexec" if name == "frcode" else "bin") / name
            current = digest(directory / relative)
            if current != digest(installed) or cc == "gcc" and current != pins["binaries"][name]["sha256"]:
                raise ValueError("canonical Findutils executable differs")
        report = dest / (cc + ".json")
        subprocess.run(["python3", ROOT / "tests/findutils-oracle-differential.py", "--gcc-build", directory,
                        "--clang-build", dest, "--output", report], check=True, stdout=subprocess.DEVNULL)
        row = json.loads(report.read_bytes())
        if not row["cases"] or row["cases"] != row["passed"]:
            raise ValueError("incomplete Findutils comparisons")
        result[cc] = {k: row[k] for k in ("cases", "passed")}
    result["updatedb_shell_sha256"] = digest(updatedb)
    return result


def error_paths(package, linked, work):
    if package == "shadow":
        profiles = [("chage", ["-l", "rustbox-shadow-no-user"]), ("getsubids", ["rustbox-shadow-no-user"])]
        directories = [Path("/rustbox-shadow/programs-gcc"), Path("/rustbox-shadow/programs-clang-18"), linked]
    else:
        profiles = [("find", [os.fsdecode(b"missing-\xff"), "-print"]), ("find", ["not-a-directory/child", "-print"])]
        directories = [Path("/rustbox-findutils/oracle-gcc/find"), Path("/rustbox-findutils/oracle-clang/find"), linked / "find"]
    outputs = []
    for number, (name, args) in enumerate(profiles):
        baseline = None
        for i, directory in enumerate(directories):
            trial = work / f"error-{number}-{i}"
            trial.mkdir()
            (trial / name).symlink_to(directory / name)
            (trial / "not-a-directory").write_bytes(b"x")
            log = trial / "memcheck"
            proc = subprocess.run(["valgrind", "--error-exitcode=99", "--leak-check=no", "--log-file=" + str(log),
                                   "./" + name, *args], cwd=trial, capture_output=True, timeout=180,
                                  stdin=subprocess.DEVNULL, env=dict(os.environ, LC_ALL="C", TZ="UTC"))
            seen = (proc.returncode, proc.stdout, proc.stderr)
            if (proc.returncode <= 0 or proc.returncode == 99 or "ERROR SUMMARY: 0 errors" not in log.read_text()
                    or baseline is not None and seen != baseline):
                raise ValueError((package, name, i, seen, baseline))
            baseline = seen
        outputs.append(dict(program=name, status=baseline[0], stdout_sha256=sha256(baseline[1]).hexdigest(),
                            stderr_sha256=sha256(baseline[2]).hexdigest()))
    return dict(memcheck_runs=len(directories)*len(profiles), errors=outputs)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("package", choices=("findutils", "shadow"))
    p.add_argument("link", type=Path)
    p.add_argument("pilot", type=Path, nargs="?")
    p.add_argument("--memcheck", action="store_true")
    a = p.parse_args()
    release = json.loads(a.link.read_bytes())
    key, = [k for k in release["source_library_sha256"] if Path(k).name.startswith("lib" + a.package + "_") and k.endswith(".a")]
    archive = ROOT / key
    if release["source_library_sha256"][key] != digest(archive):
        raise ValueError("selected archive differs")
    if a.pilot:
        rec = json.loads((a.pilot / "pilot.json").read_bytes())
        if rec["archive"] != key or rec["control_sha256"] != digest(archive) or rec["control_binary_sha256"] != release["binary"]["sha256"]:
            raise ValueError("wrong selected archive parent")
        archive = a.pilot / archive.name
        if digest(archive) != rec["candidate_sha256"]:
            raise ValueError("candidate archive differs")
    with TemporaryDirectory() as tmp:
        suites = {"shadow": shadow, "findutils": findutils}[a.package](archive, release, Path(tmp))
        checks = error_paths(a.package, Path(tmp), Path(tmp)) if a.memcheck else {}
    print(json.dumps(dict(archive_sha256=digest(archive), public=suites, **checks), sort_keys=True, indent=2))
