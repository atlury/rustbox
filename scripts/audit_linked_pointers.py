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

from build_iproute2_bridge import stage as stage_bridge
from build_e2fsprogs_checksums import SHARED_SOURCES, stage as stage_checksum
from inline_source_layout import pad_removed_items
from prune_private_inlines import replay

ROOT = Path(__file__).resolve().parents[1]
METRICS = {
    "raw_pointer_type_tokens": re.compile(rb"\*(?:mut|const)\b"),
    "raw_borrows": re.compile(rb"&raw\s+(?:mut|const)\b"),
    "as_ptr_calls": re.compile(rb"\.as_(?:mut_)?ptr\s*\("),
    "slices_from_raw_parts": re.compile(rb"\bfrom_raw_parts(?:_mut)?\s*\("),
}


def cleanup_name(archive):
    return archive.stem.removeprefix("lib").removesuffix("_audit")


def crate_for(archive, temporary):
    if "target" in archive.parts:
        return archive.parents[2]
    if archive.parent.name == "rustbox-bridge":
        engine = temporary / "bridge"
        shutil.copytree(archive.parents[1] / "bridge/bridge-final", engine)
        stage_bridge(engine, pilot=False)
        return engine
    if archive.parent.parent.name in ("rustbox-checksums", "rustbox-e2fsprogs-shared"):
        name = archive.parent.name
        engine = temporary / name
        shutil.copytree(archive.parents[2] / name / f"{name}-final", engine,
                        ignore=shutil.ignore_patterns("target"))
        stage_checksum(engine, share_bitcount=archive.parent.parent.name == "rustbox-e2fsprogs-shared")
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
    cleanups = {}
    proofs = link.get("linked_private_inline_proofs", link.get("e2fsprogs_inline_proofs", {}))
    for name, expected in sorted(link["source_library_sha256"].items()):
        path = Path(name)
        shared_object = path.name in SHARED_SOURCES and path.parent.name in ("rustbox-checksums", "rustbox-e2fsprogs-shared")
        if path.is_absolute() or (path.suffix != ".a" and not shared_object):
            excluded.append(name)
            continue
        archive = ROOT / path
        with archive.open("rb") as stream:
            hasher = hashlib.sha256()
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                hasher.update(chunk)
            if hasher.hexdigest() != expected:
                raise ValueError(f"archive differs from link report: {name}")
        crate = ROOT if shared_object else crate_for(archive, temporary)
        if not shared_object and not (crate / "Cargo.toml").is_file():
            raise ValueError(f"archive has no finalized source crate: {name}")
        package = path.relative_to("work/analysis").parts[0]
        tally = packages.setdefault(package, Counter())
        tally["standalone_objects" if shared_object else "archives"] += 1
        if shared_object or archive.parent.name == "rustbox-bridge" or archive.parent.parent.name in (
                "rustbox-checksums", "rustbox-e2fsprogs-shared"):
            manifest = json.loads(archive.with_suffix(".sources.json").read_text())
            if manifest["archive_sha256"] != expected:
                raise ValueError(f"stale compiler source list: {name}")
            files = {crate / name: sha for name, sha in manifest["sources"].items()}
        else:
            deps = archive.with_suffix(".d").read_text().splitlines()[0].split(": ", 1)[1]
            files = {ROOT / Path(name).relative_to("/work"): None
                     for name in shlex.split(deps) if name.endswith(".rs")}
        if selected := proofs.get(name):
            proof_file = archive.with_name(selected["file"])
            data = proof_file.read_bytes()
            if hashlib.sha256(data).hexdigest() != selected["sha256"]:
                raise ValueError(f"pruning evidence differs from link report: {name}")
            proof = json.loads(data)
            if (proof["archive_sha256"] != expected or set(proof["ranges"]) != set(proof["sources"])
                    or not {crate / n for n in proof["sources"]} <= files.keys()):
                raise ValueError(f"invalid private-inline provenance: {name}")
            if not crate.is_relative_to(temporary):
                original = crate
                crate = temporary / ("cargo-" + archive.stem)
                copied = {}
                for path, sha in files.items():
                    destination = crate / path.relative_to(original)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(path, destination)
                    copied[destination] = sha
                files = copied
            crate.relative_to(temporary)
            changed_sources = [crate / n for n in proof["ranges"]]
            before_bytes = sum(p.stat().st_size for p in changed_sources)
            layout = proof.get("source_layout", "lines")
            if layout not in ("lines", "byte_offsets"):
                raise ValueError(f"unknown private-inline source layout for {name}")
            if layout == "byte_offsets":
                originals = {n: (crate / n).read_bytes() for n in proof["ranges"]}
            removed = replay(crate, proof["ranges"])
            if layout == "byte_offsets":
                pad_removed_items(crate, proof["ranges"], originals)
            after_bytes = sum(p.stat().st_size for p in changed_sources)
            engine_name = cleanup_name(archive)
            if engine_name in cleanups:
                raise ValueError(f"duplicate cleanup evidence for {engine_name}")
            cleanups[engine_name] = {
                "raw_pointer_type_tokens_removed": removed,
                "source_bytes_removed": before_bytes - after_bytes,
                "private_functions_removed": sum(map(len, proof["ranges"].values())),
                "changed_files": len(proof["ranges"]),
            }
            if layout == "byte_offsets":
                cleanups[engine_name]["source_layout"] = layout
            files.update({crate / n: sha for n, sha in proof["sources"].items()})
        root_module = ROOT / f"compat/e2fsprogs/{SHARED_SOURCES[archive.name]}" if shared_object else crate / "lib.rs"
        if root_module not in files:
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
            "packages": packages, "non_applet_archive_inputs": excluded,
            **({"byte_identical_inline_cleanups": cleanups} if cleanups else {})}


def check_added_cleanups(previous_link, link, previous, current):
    """Account for each package delta when adding receipts to an otherwise identical release."""
    receipt_field = "linked_private_inline_proofs"
    for field in previous_link.keys() | link.keys():
        if field != receipt_field and (field not in previous_link or field not in link
                                       or previous_link[field] != link[field]):
            raise ValueError(f"release field changed during private-helper cleanup: {field}")
    before, after = previous_link.get(receipt_field, {}), link.get(receipt_field, {})
    for archive, receipt in before.items():
        if after.get(archive) != receipt:
            raise ValueError(f"existing cleanup receipt changed for {archive}")

    deltas = Counter()
    receipts = current.get("byte_identical_inline_cleanups", {})
    for archive in after.keys() - before.keys():
        path = Path(archive)
        package = path.relative_to("work/analysis").parts[0]
        deltas[package] += receipts[cleanup_name(path)]["raw_pointer_type_tokens_removed"]

    for package, tally in previous["packages"].items():
        updated = current["packages"][package]
        if package not in deltas and updated != tally:
            raise ValueError(f"unrelated package inventory changed: {package}")
        if tally["raw_pointer_type_tokens"] - updated["raw_pointer_type_tokens"] != deltas[package]:
            raise ValueError(f"cleanup receipts do not explain the {package} pointer count")
    if previous["all"]["raw_pointer_type_tokens"] - current["all"]["raw_pointer_type_tokens"] != sum(deltas.values()):
        raise ValueError("cleanup receipts do not explain the linked pointer count")


def measure(link):
    with tempfile.TemporaryDirectory() as temp:
        return audit(link, Path(temp))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("link_report", type=Path)
    parser.add_argument("--verify-cleanup-from", type=Path, metavar="PREVIOUS_LINK",
                        help="replay both releases and check the reduction against their added cleanup receipts")
    args = parser.parse_args()
    link = json.loads(args.link_report.read_bytes())
    current = measure(link)
    if args.verify_cleanup_from:
        previous_link = json.loads(args.verify_cleanup_from.read_bytes())
        check_added_cleanups(previous_link, link, measure(previous_link), current)
    print(json.dumps(current, indent=2, sort_keys=True))
