#!/usr/bin/env python3
"""Rebuild a second layer of unused helpers from the sources certified by a release receipt."""
# SPDX-License-Identifier: 0BSD
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

from batch_cargo_private_inlines import IDENTIFIER, INLINE
from check_cargo_private_inlines import ROOT, digest, layout, rust_inputs
from inline_source_layout import pad_removed_items
from prune_private_inlines import replay


def apply_receipt(crate, record, inputs):
    spans = record["ranges"]
    if not spans or spans.keys() != record["sources"].keys() or not set(spans) <= inputs:
        raise ValueError("cleanup must address the selected compiler inputs")
    if any(Path(name).is_absolute() or ".." in Path(name).parts for name in spans):
        raise ValueError("cleanup path escapes the selected crate")
    scope = record.get("source_directory")
    if scope is not None:
        directory = Path(scope)
        if (not directory.parts or directory.is_absolute() or ".." in directory.parts
                or any(directory not in Path(name).parents for name in spans)):
            raise ValueError("cleanup path outside the selected source directory")
    source_layout = record.get("source_layout", "lines")
    if source_layout not in ("lines", "byte_offsets"):
        raise ValueError("unknown cleanup layout")
    originals = {name: (crate / name).read_bytes() for name in spans} if source_layout == "byte_offsets" else {}
    removed = replay(crate, spans)
    if source_layout == "byte_offsets":
        pad_removed_items(crate, spans, originals)
    if any(digest(crate / name) != expected for name, expected in record["sources"].items()):
        raise ValueError("restaged source differs from the cleanup receipt")
    return removed


def read_second_layer(archive, relative, selected, parent, archive_sha):
    checksum = selected["sha256"]
    expected = archive.with_suffix(f".layer2-{checksum}.json")
    if selected["file"] != expected.name:
        raise ValueError(f"unexpected second-layer receipt filename: {relative}")
    data = expected.read_bytes()
    if hashlib.sha256(data).hexdigest() != checksum:
        raise ValueError(f"second-layer receipt differs from release: {relative}")
    report = json.loads(data)
    record = report["second_layer"]
    if (report["archive"] != str(relative) or report["archive_sha256"] != archive_sha
            or report["parent"] != parent or record["archive_sha256"] != archive_sha
            or not record["ranges"]):
        raise ValueError(f"invalid second-layer provenance: {relative}")
    return report


def baseline(release, archive):
    layout(archive)
    if archive.parts[3] not in ("translations", "program-translations"):
        raise ValueError("expected a linked Cargo translation")
    sha = release["source_library_sha256"][str(archive)]
    if digest(ROOT / archive) != sha:
        raise ValueError("archive differs from release")
    selection = release["linked_private_inline_proofs"][str(archive)]
    proof_path = (ROOT / archive).with_name(selection["file"])
    if digest(proof_path) != selection["sha256"]:
        raise ValueError("previous receipt differs from release")
    parent = json.loads(proof_path.read_bytes())
    if parent["archive_sha256"] != sha:
        raise ValueError("previous receipt was issued for a different archive")
    return sha, selection, parent


def new_leaf_estimate(data, ranges):
    before = Counter(IDENTIFIER.findall(data))
    parts = []
    end = 0
    for start, stop in ranges:
        if not end <= start < stop <= len(data):
            raise ValueError("invalid parent source ranges")
        parts.append(data[end:start])
        end = stop
    current = b"\n".join([*parts, data[end:]])
    after = Counter(IDENTIFIER.findall(current))
    return sum(after[name] == 1 and before[name] > 1 for name in INLINE.findall(current))


def rank(release, *, grouped=False):
    rows = []
    for name in release["linked_private_inline_proofs"]:
        if name in release.get("linked_second_inline_proofs", {}):
            continue
        archive = Path(name)
        if grouped:
            if archive.parts[3] != "program-translations" or "cargo-target" not in archive.parts:
                continue
        elif archive.parts[3] != "translations":
            continue
        _, _, parent = baseline(release, archive)
        source, _ = layout(archive)
        inputs = rust_inputs(ROOT / archive)
        if not {source / n for n in parent["ranges"]} <= inputs:
            raise ValueError("unexpected compiler input in parent receipt")
        count = sum(new_leaf_estimate((ROOT / source / n).read_bytes(), ranges)
                    for n, ranges in parent["ranges"].items())
        rows.append({"archive": name, "estimated_new_leaves": count})
    return sorted(rows, key=lambda row: (-row["estimated_new_leaves"], row["archive"]))


def check_layer(release, archive, *, publish=False, expected_receipt=None):
    sha, selection, parent = baseline(release, archive)
    source, base = layout(archive)
    inputs = {str(p.relative_to(source)) for p in rust_inputs(ROOT / archive)}
    with tempfile.TemporaryDirectory(dir=ROOT / "work/analysis") as directory:
        scratch = Path(directory)
        crate, target = scratch / "source", scratch / "target"
        shutil.copytree(ROOT / source, crate, ignore=shutil.ignore_patterns("target"))
        target.mkdir()
        apply_receipt(crate, parent, inputs)
        for path in (crate, target):
            (path / ".rustbox-inline-scratch").write_text(sha)
        scope = parent.get("source_directory")
        registry = [] if archive.parts[2].startswith("e2fsprogs-") else [
            "-v", "rustbox-pointer-cargo-registry:/root/.cargo/registry:ro"]
        subprocess.run([
            "docker", "run", "--rm", "--network", "none", "--platform", "linux/amd64",
            "--workdir", "/work", "-v", f"{ROOT}:/work:ro",
            *registry,
            "-v", f"{crate}:/work/{source}", "-v", f"{target}:/work/{base}",
            "rustbox-e2fsprogs:2026-11-24", "python3", "-B", "/work/scripts/check_cargo_private_inlines.py",
            str(archive), "--verify-mounted-copy", sha, *(["--source-dir", scope] if scope else []),
        ], check=True)
        next_record = json.loads((target / ".rustbox-private-inlines.json").read_bytes())
        if (digest(target / "release" / archive.name) != sha or next_record["archive_sha256"] != sha
                or next_record.get("source_directory") != scope):
            raise ValueError("second build differs from the selected release or source scope")
        # Reconstruct both layers independently from pristine inputs.
        check = scratch / "replay"
        check.mkdir()
        for name in parent["ranges"].keys() | next_record["ranges"].keys():
            if name not in inputs:
                raise ValueError("unexpected compiler input in second layer")
            out = check / name
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / source / name, out)
        apply_receipt(check, parent, inputs)
        if not next_record["ranges"]:
            return {"archive": str(archive), "archive_sha256": sha, "parent": selection,
                    "private_functions_removed": 0, "raw_pointer_type_tokens_removed": 0}
        removed = apply_receipt(check, next_record, inputs)
        report = {"archive": str(archive), "archive_sha256": sha, "parent": selection,
                "private_functions_removed": sum(map(len, next_record["ranges"].values())),
                "raw_pointer_type_tokens_removed": removed, "second_layer": next_record}
        if publish:
            data = (json.dumps(report, sort_keys=True) + "\n").encode()
            checksum = hashlib.sha256(data).hexdigest()
            receipt = (ROOT / archive).with_suffix(f".layer2-{checksum}.json")
            selected = {"file": receipt.name, "sha256": checksum}
            if expected_receipt is not None and selected != expected_receipt:
                raise ValueError("newly compiled layer differs from the pinned release receipt")
            # Both files are on the same filesystem. Readers always see a complete archive.
            pending = scratch / "receipt.json"
            pending.write_bytes(data)
            (target / "release" / archive.name).replace(ROOT / archive)
            pending.replace(receipt)
        return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("link_report", type=Path)
    parser.add_argument("archive", type=Path, nargs="?")
    parser.add_argument("output", type=Path, nargs="?", help="new experiment report outside the release")
    parser.add_argument("--rank", action="store_true", help="estimate newly unreferenced functions by archive")
    parser.add_argument("--grouped", action="store_true", help="rank Cargo-built engines of multi-engine packages")
    parser.add_argument("--publish", action="store_true", help="install the byte-identical archive and its receipt")
    args = parser.parse_args()
    release = json.loads(args.link_report.read_bytes())
    if args.rank:
        if args.archive or args.output or args.publish:
            parser.error("--rank needs only the release report")
        print(json.dumps(rank(release, grouped=args.grouped), indent=2))
        raise SystemExit(0)
    if args.grouped:
        parser.error("--grouped applies only to ranking")
    if not args.archive or not args.output:
        parser.error("provide the archive and output path, or use --rank")
    report = check_layer(release, args.archive, publish=args.publish)
    with args.output.open("x") as stream:
        json.dump(report, stream, sort_keys=True)
        stream.write("\n")
    print(json.dumps({k: report[k] for k in ("archive", "private_functions_removed", "raw_pointer_type_tokens_removed")}))
