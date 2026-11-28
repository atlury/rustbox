#!/usr/bin/env python3
"""Compare GNU tar archive bytes for both built-in exclusion tables on raw Unix names."""
# SPDX-License-Identifier: GPL-3.0-or-later
import argparse
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
import subprocess
import tarfile
from tempfile import TemporaryDirectory

from build_tar_exclusion_tables import canonical_patterns, substitute
from build_checked_errno import replay
from check_cargo_private_inlines import ROOT, digest

PKG = ROOT / "work/analysis/tar-1.35"
ENV = dict(os.environ, LC_ALL="C", LANG="C", TZ="UTC", TAR_OPTIONS="")
VCS, BACKUPS = "--exclude-vcs", "--exclude-backups"


def fixture(directory):
    names = canonical_patterns()["vcs_file_table"]
    near = [b"keep", b"~prefix", b"x.#x", b"#near", b".git-extra", b"plain-\xff"]
    backups = [b".#editor", b"#draft#", b"plain~", b"raw-\xff~"]
    leaves = set()
    for prefix in (b"top", b"top/nested"):
        for name in [*names, *backups, *near]:
            leaves.add(prefix + b"/" + name)
    for name in [*names, *backups, *near]:
        leaves.add(b"dirs/" + name + b"/child")
    for leaf in sorted(leaves):
        path = directory / os.fsdecode(leaf)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(leaf)
    return leaves, set(names), set(backups)


def exercise(programs, directory, memcheck=False):
    source = directory / "tree"
    source.mkdir()
    leaves, vcs, backups = fixture(source)
    options = [(), (VCS,), (BACKUPS,), (VCS, BACKUPS), (BACKUPS, VCS), (VCS, VCS),
               (BACKUPS, BACKUPS), ("--no-wildcards", BACKUPS), ("--anchored", VCS),
               ("--no-recursion", VCS), (VCS, "--exclude=keep"), ("--exclude=keep", BACKUPS, VCS)]
    observed = []
    for flags in options:
        arguments = ["-cf", "-", "--format=ustar", "--blocking-factor=1", "--sort=name",
                     "--owner=0", "--group=0", "--mtime=@946684800", *flags, "-C", source, "."]
        expected = None
        for label, invocation in programs.items():
            p = subprocess.run([*invocation, *arguments], env=ENV, capture_output=True, timeout=90)
            if p.returncode or p.stderr:
                raise ValueError((flags, label, p.returncode, p.stderr))
            if expected is None:
                expected = p.stdout
            elif p.stdout != expected:
                raise ValueError(f"{label} archive bytes differed for {flags!r}")
        with tarfile.open(fileobj=BytesIO(expected), mode="r:") as archive:
            members = {os.fsencode(m.name.removeprefix("./")) for m in archive if m.isfile()}
        if not flags or set(flags) <= {VCS, BACKUPS}:
            excluded = (vcs if VCS in flags else set()) | (backups if BACKUPS in flags else set())
            wanted = {name for name in leaves if excluded.isdisjoint(name.split(b"/"))}
            if members != wanted:
                raise ValueError((flags, wanted.symmetric_difference(members)))
        observed.append(dict(options=flags, regular_members=len(members), archive_sha256=sha256(expected).hexdigest()))
        if memcheck and flags == (VCS, BACKUPS):
            log = directory / "memcheck.log"
            p = subprocess.run(["valgrind", "--error-exitcode=99", "--leak-check=full", "--errors-for-leak-kinds=definite,indirect",
                                "--log-file=" + str(log), *programs["candidate"], *arguments], capture_output=True, env=ENV, timeout=240)
            if p.returncode or p.stdout != expected or p.stderr or "ERROR SUMMARY: 0 errors" not in log.read_text():
                raise ValueError("tar exclusions differ under Memcheck")
    return dict(profiles=observed, fixture_files=len(leaves), memcheck_runs=int(memcheck))


def compare(pilot, link, exercise_cases=exercise):
    with TemporaryDirectory() as temp:
        root = Path(temp)
        programs = {cc:[PKG / "oracle" / (cc + "-root/usr/bin/tar")] for cc in ("gcc", "clang")}
        row = {}
        if pilot:
            row = json.loads((pilot / "pilot.json").read_bytes())
            key = row["archive"]
            release = json.loads(link.read_bytes())
            if (release["source_library_sha256"][key] != row["control_sha256"] or digest(ROOT / key) != row["control_sha256"]
                    or digest(pilot / Path(key).name) != row["candidate_sha256"]
                    or row["control_binary_sha256"] != release["binary"]["sha256"]):
                raise ValueError("tar archive or executable differs from the compiler receipt")
            residue = sorted((PKG / "hybrid-artifacts/c-residue").glob("*.o"))
            for obj in residue:
                if digest(obj) != release["source_library_sha256"][str(obj.relative_to(ROOT))]:
                    raise ValueError("tar C residue changed")
            for label, lib in (("control", ROOT / key), ("candidate", pilot / Path(key).name)):
                exe = root / label / "tar"
                exe.parent.mkdir()
                subprocess.run(["clang-18", "-O2", "-DRUSTBOX_ENTRY=rustbox_tar_main", "-Wl,--gc-sections",
                                "-o", exe, ROOT / "bridges/tar_main.c", *residue, lib, "-lacl", "-ldl", "-lpthread",
                                "-lm", "-lrt", "-lutil"], check=True)
                programs[label] = [exe]
        result = exercise_cases(programs, root, memcheck=bool(pilot))
        return dict(result, archive=row, executable_sha256={label:digest(program[0]) for label,program in programs.items()},
                    oracle_driver_sha256=digest(Path(exercise_cases.__code__.co_filename)))


def main(driver, transform, exercise_cases):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mounted", action="store_true")
    p.add_argument("--link", type=Path)
    p.add_argument("--pilot", type=Path)
    a = p.parse_args()
    if bool(a.link) != bool(a.pilot):
        p.error("supply both the release and the rebuilt tar archive")
    if a.mounted:
        print(json.dumps(compare(a.pilot, a.link, exercise_cases), sort_keys=True, indent=2))
    else:
        if a.pilot:
            key = json.loads((a.pilot / "pilot.json").read_bytes())["archive"]
            replay(a.link, key, a.pilot, transform=transform)
        args = ["--link", Path("/work") / a.link.resolve().relative_to(ROOT), "--pilot", Path("/work") / a.pilot.resolve().relative_to(ROOT)] if a.pilot else []
        subprocess.run(["docker", "run", "--rm", "--network", "none", "--platform", "linux/amd64", "-v", f"{ROOT}:/work:ro",
                        "-w", "/tmp", "rustbox-e2fsprogs:2026-11-24", "python3", "-B", str(Path("/work/scripts") / driver),
                        "--mounted", *args], check=True)


if __name__ == "__main__":
    main(Path(__file__).name, substitute, exercise)
