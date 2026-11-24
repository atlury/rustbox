#!/usr/bin/env python3
"""Measure Rust sources of applet archives selected by a Rustbox Linux link report."""
# SPDX-License-Identifier: 0BSD

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import shlex
import shutil
import tempfile

from build_iproute2_bridge import stage

ROOT = Path(__file__).resolve().parents[1]
METRICS = {
    "raw_pointer_type_tokens": re.compile(rb"\*(?:mut|const)\b"),
    "raw_borrows": re.compile(rb"&raw\s+(?:mut|const)\b"),
    "as_ptr_calls": re.compile(rb"\.as_(?:mut_)?ptr\s*\("),
    "slices_from_raw_parts": re.compile(rb"\bfrom_raw_parts(?:_mut)?\s*\("),
}


def crate_for(archive, temporary):
    if "target" in archive.parts:
        return archive.parents[2]
    if archive.parent.name == "rustbox-bridge":
        engine = temporary / "bridge"
        shutil.copytree(archive.parents[1] / "bridge/bridge-final", engine)
        stage(engine, pilot=False)
        return engine
    target = next(p for p in archive.parents if p.name == "cargo-target")
    name = archive.name.removeprefix("lib").removesuffix("_audit.a")
    suffix = "stable" if archive.parent == target / "release" else "final"
    return target.parent / name / f"{name}-{suffix}"


def audit(link, temporary):
    packages = {}
    unique = {}
    measured = Counter()
    excluded = []
    for name, expected in sorted(link["source_library_sha256"].items()):
        path = Path(name)
        if path.is_absolute() or path.suffix != ".a":
            excluded.append(name)
            continue
        archive = ROOT / path
        with archive.open("rb") as stream:
            hasher = hashlib.sha256()
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                hasher.update(chunk)
            if hasher.hexdigest() != expected:
                raise ValueError(f"archive differs from link report: {name}")
        crate = crate_for(archive, temporary)
        if not (crate / "Cargo.toml").is_file():
            raise ValueError(f"archive has no finalized source crate: {name}")
        package = path.relative_to("work/analysis").parts[0]
        tally = packages.setdefault(package, Counter())
        tally["archives"] += 1
        if archive.parent.name == "rustbox-bridge":
            manifest = json.loads(archive.with_suffix(".sources.json").read_text())
            if manifest["archive_sha256"] != expected:
                raise ValueError("stale bridge compiler source list")
            files = {crate / name: sha for name, sha in manifest["sources"].items()}
        else:
            deps = archive.with_suffix(".d").read_text().splitlines()[0].split(": ", 1)[1]
            files = {ROOT / Path(name).relative_to("/work"): None
                     for name in shlex.split(deps) if name.endswith(".rs")}
        if crate / "lib.rs" not in files:
            raise ValueError(f"unexpected compiler inputs for {archive}")
        for file, source_sha in files.items():
            file.relative_to(crate)
            data = file.read_bytes()
            digest = hashlib.sha256(data).digest()
            if source_sha and digest.hex() != source_sha:
                raise ValueError(f"restaged source differs from linked version: {file.name}")
            if digest not in unique:
                unique[digest] = Counter({k: len(regex.findall(data)) for k, regex in METRICS.items()})
            tally.update(unique[digest])
            tally["files"] += 1
    for tally in packages.values():
        measured.update(tally)
    distinct = Counter()
    for counts in unique.values():
        distinct.update(counts)
    return {"binary_sha256": link["binary"]["sha256"], "all": measured,
            "unique_files": len(unique), "counting_identical_files_once": distinct,
            "packages": packages, "non_applet_archive_inputs": excluded}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("link_report", type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as temp:
        print(json.dumps(audit(json.loads(args.link_report.read_text()), Path(temp)), indent=2, sort_keys=True))
