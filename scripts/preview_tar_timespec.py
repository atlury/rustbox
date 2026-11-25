#!/usr/bin/env python3
"""Relink the complete selected multicall in isolation and exercise the borrowed GNU tar timestamps."""
# SPDX-License-Identifier: GPL-3.0-or-later
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
from tempfile import TemporaryDirectory

from build_tar_timespec_pilot import ARCHIVE
from check_cargo_private_inlines import ROOT, digest
from link_rustbox_multicall import namespace_tar_inputs

COMMAND_SHA = "411fb9679311197f0273b170625142d2fa40e9016b74ba6255e2c4fe02f7183e"


def commands(elf, tmp):
    driver = ROOT / "tests/tar-oracle-differential.py"
    canonical = ROOT / "work/analysis/tar-1.35/oracle"
    cases = {}
    for mode in ("applet", "subcommand"):
        stage = tmp / mode
        for utility, path in (("tar", "usr/bin/tar"), ("rmt", "usr/libexec/rmt")):
            entry = stage / path
            entry.parent.mkdir(parents=True, exist_ok=True)
            if mode == "applet":
                entry.symlink_to(elf)
            else:
                entry.write_text("#!/bin/sh\nexec " + shlex.quote(str(elf)) + " " + utility + ' "$@"\n')
                entry.chmod(0o755)
        for compiler in ("gcc", "clang"):
            result = tmp / f"{mode}-{compiler}.json"
            subprocess.run(["python3", driver, "--gcc-root", canonical / (compiler + "-root"), "--clang-root", stage,
                            "--output", result], check=True, stdout=subprocess.DEVNULL)
            row = json.loads(result.read_bytes())
            if row["cases"] != 18 or row["passed"] != row["cases"]:
                raise ValueError("tar/rmt public dispatch differs from its canonical build")
            cases[f"{mode}-{compiler}"] = row["passed"]
    src, dest = tmp / "source", tmp / "extracted"
    src.mkdir()
    dest.mkdir()
    (src / "data").write_bytes(b"tar timestamp probe\n")
    (src / "link").symlink_to("data")
    stamp = 1710000000123456789
    for child in src.iterdir():
        os.utime(child, ns=(stamp, stamp), follow_symlinks=False)
    archive = tmp / "timestamps.tar"
    for i, args in enumerate((["-c", "--format=pax", "-f", archive, "-C", src, "data", "link"],
                              ["-xf", archive, "-C", dest])):
        report = tmp / f"valgrind-{i}.log"
        subprocess.run(["valgrind", "--leak-check=full", "--errors-for-leak-kinds=definite,indirect,possible",
                        "--error-exitcode=99", "--log-file=" + str(report), elf, "tar", *args], check=True)
        if "ERROR SUMMARY: 0 errors" not in report.read_text():
            raise ValueError("tar multicall Memcheck failed")
    if ((dest / "data").read_bytes() != (src / "data").read_bytes() or os.readlink(dest / "link") != "data"
            or any(p.lstat().st_mtime_ns != stamp for p in dest.iterdir())):
        raise ValueError("multicall extraction lost the file, symlink or nanosecond timestamps")
    return dict(canonical_cases=cases, memcheck_runs=2, restored_file_and_symlink_mtime_ns=stamp,
                command_driver_sha256=digest(driver))


def preview(parent, log, pilot, output):
    release = json.loads(parent.read_bytes())
    row = json.loads((pilot / "pilot.json").read_bytes())
    qualified = json.loads((ROOT / "evidence/tar-borrowed-timespec-pilot.json").read_bytes())
    if any(qualified[k] != value for k, value in row.items()) or release["source_library_sha256"].get(ARCHIVE) != row["control_sha256"]:
        raise ValueError("tar pilot differs from the qualified archive or selected parent")
    raw = [shlex.split(s) for s in log.read_text().splitlines() if s.startswith("clang-18 -DSINGLE_BINARY")]
    if len(raw) != 1 or sha256(json.dumps(raw[0], separators=(",", ":")).encode()).hexdigest() != COMMAND_SHA:
        raise ValueError("unrecognized final Linux link command")
    build = Path("/rustbox-coreutils/canonical-clang-no-security-compdb")
    if digest(build / "src/rustbox") != release["binary"]["sha256"]:
        raise ValueError("installed ELF differs from the specified parent")
    residues = sorted((ROOT / "work/analysis/tar-1.35/hybrid-artifacts/c-residue").glob("*.o"))
    if len(residues) != 4 or any(release["source_library_sha256"][str(p.relative_to(ROOT))] != digest(p) for p in residues):
        raise ValueError("tar C linkage inputs differ from the specified parent")
    checks = {}
    with TemporaryDirectory() as scratch, TemporaryDirectory(dir=output.parent) as workspace:
        result = Path(workspace) / "result"
        result.mkdir()
        for name, path in (("parent", ROOT / ARCHIVE), ("candidate", pilot / Path(ARCHIVE).name)):
            expected = row["control_sha256" if name == "parent" else "candidate_sha256"]
            if digest(path) != expected:
                raise ValueError(f"unexpected {name} archive")
            stage = Path(scratch) / name
            archive, objs, symbols, imports = namespace_tar_inputs(path, residues, release["acl_namespaced_symbols"], stage)
            if symbols != release["tar_namespaced_symbols"] or imports != release["tar_acl_imports"]:
                raise ValueError("tar symbol names or ACL imports changed")
            cmd = [str(build / "lib/.rustbox-libcoreutils.a") if x == "lib/libcoreutils.a" else x for x in raw[0]]
            for obj in [archive, *objs]:
                old = build / "src/.rustbox-tar" / obj.name
                if cmd.count(str(old)) != 1 or ((name == "parent" or obj != archive) and digest(obj) != digest(old)):
                    raise ValueError(f"unexpected previous linker input {obj.name}")
                cmd[cmd.index(str(old))] = str(obj)
            elf = stage / "rustbox"
            cmd[cmd.index("-o") + 1] = str(elf)
            cmd[cmd.index("-Wl,-Map=src/rustbox.map")] = "-Wl,-Map=" + str(stage / "link.map")
            subprocess.run(cmd, cwd=build, check=True)
            if name == "parent" and digest(elf) != release["binary"]["sha256"]:
                raise ValueError("isolated control did not reproduce the entire linked executable")
            stripped = stage / "stripped"
            subprocess.run(["strip", "--strip-all", "-o", stripped, elf], check=True)
            checks[name] = dict(bytes=elf.stat().st_size, sha256=digest(elf), stripped_bytes=stripped.stat().st_size,
                                stripped_sha256=digest(stripped), archive_sha256=expected)
            if name == "candidate":
                checks.update(commands(elf, stage))
                shutil.copy2(elf, result / "rustbox")
        checks.update(parent_link_report_sha256=digest(parent), linker_command_sha256=COMMAND_SHA)
        (result / "comparison.json").write_text(json.dumps(checks, indent=2, sort_keys=True) + "\n")
        result.rename(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("parent_link", "parent_build_log", "pilot", "new_directory"):
        parser.add_argument(arg, type=Path)
    args = parser.parse_args()
    preview(args.parent_link, args.parent_build_log, args.pilot, args.new_directory)
