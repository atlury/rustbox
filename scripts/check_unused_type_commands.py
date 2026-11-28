#!/usr/bin/env python3
"""Exercise the canonical command suites for the archives selected in a grouped unused-type link."""
# SPDX-License-Identifier: GPL-3.0-or-later
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory

from check_cargo_private_inlines import ROOT, digest
from qualify_iproute2_combined_names import write_result


def run_suite(package, cc, elf, stage):
    stage.mkdir()
    name = package.split("-")[0]
    baseline = json.loads((ROOT / "evidence" / (package + "-oracle.json")).read_bytes())
    directory = ROOT / "work/analysis" / package / "oracle"
    if name == "curl":
        reference = baseline["tests"]["differential"]
    elif name == "gawk":
        reference = baseline["differential"]
    else:
        reference = baseline["cross_compiler_differential"]
    expected = reference.get("comparisons", reference.get("cases"))
    driver = ROOT / "tests" / (name + "-oracle-differential.py")
    pins = {}
    oracle = stage / "canonical"
    oracle.mkdir()

    def canonical(tool):
        key = baseline.get("binaries", {})
        if name == "acl":
            pin = key[tool][cc]["sha256"]
        elif name == "diffutils":
            pin = key[cc][tool]["sha256"]
        else:
            pin = key[cc]["sha256"]
        path = directory / f"{tool}-{cc}"
        local = oracle / path.name
        shutil.copy2(path, local)
        if digest(local) != pin:
            raise ValueError(f"{tool} {cc} oracle differs from the pinned binary")
        pins[tool] = pin
        return local

    if name == "gawk":
        source = Path("/rustbox-gawk") / ("oracle-" + cc)
        proof = json.loads((ROOT / "evidence/gawk-errno-archive.json").read_bytes())
        if digest(source / "gawk") != proof["public"]["canonical"][cc]:
            raise ValueError("GNU awk oracle differs")
        pins["gawk"] = proof["public"]["canonical"][cc]
        dispatch = stage / ("gawk-" + cc)
        dispatch.mkdir()
        (dispatch / "gawk").symlink_to(elf)
        (dispatch / "extension").symlink_to(ROOT / "build/gawk-5.4.0-hybrid/extension")
        args = ["--gcc-build", source, "--clang-build", dispatch]
    elif name == "acl":
        for tool in ("chacl", "getfacl", "setfacl"):
            canonical(tool)
            (stage / (tool + "-" + cc)).symlink_to(elf)
        args = ["--gcc-directory", oracle, "--gcc-suffix", cc, "--clang-directory", stage, "--clang-suffix", cc]
    elif name == "diffutils":
        args = []
        for tool in ("cmp", "diff", "diff3", "sdiff"):
            args.extend(["--gcc-" + tool, canonical(tool), "--clang-" + tool, elf])
    elif name in ("grep", "curl"):
        candidate = elf
        if name == "curl":
            candidate = stage / cc / "curl"
            candidate.parent.mkdir()
            candidate.symlink_to(elf)
        args = ["--gcc", canonical(name), "--clang", candidate]
    else:
        raise ValueError(f"missing canonical suite for {package}")
    out = stage / f"{name}-{cc}.json"
    print(f"Checking {package} against {cc}", flush=True)
    subprocess.run([sys.executable, driver, *args, "--output", out], check=True)
    data = json.loads(out.read_bytes())
    passed = data.get("passed", data.get("comparisons") if data.get("gcc_clang_exact") else None)
    if not expected or passed != expected:
        raise ValueError(f"incomplete {name} {cc} differential")
    return name + "-" + cc, dict(passed=passed, canonical_sha256=pins, report_sha256=digest(out), driver_sha256=digest(driver))


def check(elf, selection, comparison, *, side="candidate"):
    report = json.loads(comparison.read_bytes())
    checksum = report[side]["sha256"]
    if report["selection_sha256"] != digest(selection) or checksum != digest(elf):
        raise ValueError("selection, link and executable must match")
    groups = {Path(k).parts[2] for k in json.loads(selection.read_bytes())["archives"]}
    if not groups:
        raise ValueError("no packages selected")
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        local = root / "rustbox"
        shutil.copy2(elf, local)
        if digest(local) != checksum:
            raise ValueError("staged ELF changed")
        with ThreadPoolExecutor(max_workers=2) as workers:
            jobs = [workers.submit(run_suite, package, cc, local, root / (package + "-" + cc))
                    for package in sorted(groups) for cc in ("gcc", "clang")]
            results = dict(job.result() for job in jobs)
    return dict(binary_sha256=checksum, side=side, selection_sha256=digest(selection), suites=results,
                comparisons=sum(r["passed"] for r in results.values()))



if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ("elf", "selection", "comparison", "output"):
        parser.add_argument(field, type=Path)
    parser.add_argument("--side", choices=["parent", "candidate"], default="candidate")
    a = parser.parse_args()
    write_result(a.output, check(a.elf.resolve(), a.selection, a.comparison, side=a.side))
