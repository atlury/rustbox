#!/usr/bin/env python3
"""Prepare pinned second-pass Cargo archives and bind their receipts at link time."""
# SPDX-License-Identifier: 0BSD
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import tempfile

from batch_cargo_private_inlines import release_archives
from check_cargo_private_inlines import ROOT, digest, layout
from check_next_inline_layer import check_layer, read_second_layer


def manifest(repository):
    path = repository / "batches/multicall-second-inline-proofs.json"
    return json.loads(path.read_bytes())


def linked_layers(repository, parents, source_hashes):
    records = manifest(repository)
    for name, selected in records.items():
        relative = Path(name)
        layout(relative)
        if name not in parents or relative.parts[3] not in ("translations", "program-translations"):
            raise ValueError(f"missing linked Cargo parent for {name}")
        archive = repository / relative
        read_second_layer(archive, relative, selected, parents[name], source_hashes[name])
    return records


def prepare(records, args_file):
    enrolled = {str(path): package for package, path in release_archives(args_file).values()}
    grouped = {"e2fsprogs", "iproute2", "inetutils"}
    for name in records.keys() - enrolled.keys():
        relative = Path(name)
        layout(relative)
        package = relative.parts[2].split("-", 1)[0]
        if relative.parts[3] == "program-translations" and package in grouped:
            index = ROOT / f"work/analysis/{package}-cargo-inline-proofs.json"
            if name in json.loads(index.read_bytes()):
                enrolled[name] = package
    if not records.keys() <= enrolled.keys():
        raise ValueError("a second-layer archive is missing from the release arguments")

    def verify(item):
        name, selected = item
        relative = Path(name)
        archive = ROOT / relative
        index = ROOT / f"work/analysis/{enrolled[name]}-cargo-inline-proofs.json"
        parent = json.loads(index.read_bytes())[name]
        sha = digest(archive)
        # If the immutable receipt is missing, reproduce it using the current
        # release inputs. The candidate must match both pinned digests.
        if not archive.with_name(selected["file"]).is_file():
            release = {"source_library_sha256": {name: sha}, "linked_private_inline_proofs": {name: parent}}
            check_layer(release, relative, publish=True, expected_receipt=selected)
        read_second_layer(archive, relative, selected, parent, sha)

    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(verify, records.items()))


def enroll(repository, link_path, results_paths):
    link_bytes = link_path.read_bytes()
    release = json.loads(link_bytes)
    link_sha = hashlib.sha256(link_bytes).hexdigest()
    records = manifest(repository)
    if records != release.get("linked_second_inline_proofs", {}):
        raise ValueError("start enrollment from the manifest in the selected release")
    for results_path in results_paths:
        batch = json.loads(results_path.read_bytes())
        if batch["link_sha256"] != link_sha:
            raise ValueError("batch belongs to a different release")
        for name, entry in batch["archives"].items():
            if entry["status"] != "verified":
                raise ValueError(f"unfinished archive in batch: {name}")
            if entry["helpers"] == 0:
                if entry["pointers"] or "receipt" in entry:
                    raise ValueError("empty cleanup has a nonempty result")
                continue
            relative = Path(name)
            layout(relative)
            sha = release["source_library_sha256"][name]
            archive = repository / relative
            if digest(archive) != sha:
                raise ValueError(f"archive differs from the selected release: {name}")
            receipt = entry["receipt"]
            report = read_second_layer(archive, relative, receipt, release["linked_private_inline_proofs"][name], sha)
            if (entry["helpers"] != report["private_functions_removed"]
                    or entry["pointers"] != report["raw_pointer_type_tokens_removed"]):
                raise ValueError("batch totals differ from the compiled receipt")
            if records.setdefault(name, receipt) != receipt:
                raise ValueError("conflicting second-layer receipts")
    destination = repository / "batches/multicall-second-inline-proofs.json"
    with tempfile.NamedTemporaryFile(mode="w", dir=destination.parent, delete=False) as pending:
        json.dump(records, pending, indent=2, sort_keys=True)
        pending.write("\n")
    staged = Path(pending.name)
    staged.chmod(destination.stat().st_mode & 0o777)
    staged.replace(destination)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--enroll-results", type=Path, nargs="+", help="enroll verified batch result files")
    parser.add_argument("--from-link", type=Path, help="release used when building those batches")
    args = parser.parse_args()
    if bool(args.from_link) != bool(args.enroll_results):
        parser.error("use --enroll-results and --from-link together")
    if args.enroll_results:
        enroll(ROOT, args.from_link, args.enroll_results)
    else:
        prepare(manifest(ROOT), ROOT / "batches/multicall-inline-archives.args")
