#!/usr/bin/env python3
"""Build and verify E2fsprogs fixed-array archives without replacing their production controls."""
# SPDX-License-Identifier: GPL-2.0-only
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import shutil
import tempfile

from build_e2fsprogs_checksums import CONSUMERS
from check_cargo_private_inlines import ROOT, digest
from check_e2fsprogs_dirhash_arrays import compile_candidate


def candidate_path(base, sha):
    engine = base.parent.name
    if (engine not in CONSUMERS or len(base.parts) != 7 or base.parts[:2] != ("work", "analysis")
            or not base.parts[2].startswith("e2fsprogs-")
            or base.parts[3:5] != ("program-translations", "rustbox-e2fsprogs-shared")
            or base.name != f"lib{engine}_audit.a" or len(sha) != 64
            or any(ch not in "0123456789abcdef" for ch in sha)):
        raise ValueError(f"unexpected directory hash archive selection: {base}")
    return base.parents[2] / "rustbox-dirhash-arrays" / engine / sha / base.name


def validate(link, base, record):
    name = str(base)
    if (record["production_sha256"] != link["source_library_sha256"][name]
            or record["inlines"] != link["linked_private_inline_proofs"][name]
            or record["second_inlines"] != link.get("linked_second_inline_proofs", {}).get(name)
            or record["declarations"] != link.get("linked_foreign_declaration_proofs", {}).get(name)
            or record["raw_offset_accesses_replaced"] != 40):
        raise ValueError(f"directory hash proof differs from its compiler inputs: {base}")
    return candidate_path(base, record["candidate_sha256"])


def build(link, base, pinned=None, repository=ROOT):
    with tempfile.TemporaryDirectory() as tmp:
        scratch = Path(tmp)
        record = compile_candidate(link, base, scratch)
        output = repository / validate(link, base, record)
        if pinned is not None and record != pinned:
            raise ValueError(f"directory hash build differs from its pinned result: {base}")
        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=output.parent) as temporary:
            staged = Path(temporary) / base.name
            shutil.copyfile(scratch / base.name, staged)
            if digest(staged) != record["candidate_sha256"]:
                raise ValueError(f"directory hash archive changed before publication: {base}")
            staged.replace(output)
    return record


def control_view(link):
    """Recover the still-addressable input archives for replaying earlier source receipts."""
    records = link.get("e2fsprogs_dirhash_arrays", {})
    if not records:
        return link
    hashes = link["source_library_sha256"].copy()
    for name, record in records.items():
        candidate = str(candidate_path(Path(name), record["candidate_sha256"]))
        if name in hashes or hashes.pop(candidate, None) != record["candidate_sha256"]:
            raise ValueError(f"array candidate differs from the actual linker input: {name}")
        hashes[name] = record["production_sha256"]
    control = dict(link, source_library_sha256=hashes)
    for name, record in records.items():
        validate(control, Path(name), record)
    return control


def prepare(link, manifest, repository):
    records = json.loads(manifest.read_bytes())
    controls = {name for name in link["linked_private_inline_proofs"]
                if Path(name).parent.parent.name == "rustbox-e2fsprogs-shared"}
    if records.keys() != controls or {Path(name).parent.name for name in controls} != set(CONSUMERS):
        raise ValueError("directory hash manifest must cover the release's 13 staged engines")

    def verify(item):
        name, record = item
        base = Path(name)
        target = repository / validate(link, base, record)
        if not target.is_file():
            build(link, base, pinned=record, repository=repository)
        if digest(target) != record["candidate_sha256"]:
            raise ValueError(f"directory hash candidate differs from its pinned archive: {name}")

    with ThreadPoolExecutor(max_workers=3) as workers:
        list(workers.map(verify, records.items()))
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("link", type=Path)
    parser.add_argument("output", type=Path, help="new directory for per-engine receipts and final manifest")
    parser.add_argument("--jobs", type=int, default=2)
    args = parser.parse_args()
    if args.jobs < 1:
        parser.error("--jobs must be positive")
    data = args.link.read_bytes()
    link = control_view(json.loads(data))
    controls = sorted(Path(name) for name in link["linked_private_inline_proofs"]
                      if Path(name).parent.parent.name == "rustbox-e2fsprogs-shared")
    if sorted(base.parent.name for base in controls) != sorted(CONSUMERS):
        raise ValueError("expected each of the shared-checksum engines exactly once")
    args.output.mkdir()

    def check(base):
        record = build(link, base)
        (args.output / (base.parent.name + ".json")).write_text(json.dumps(record, sort_keys=True) + "\n")
        print(f"{base.parent.name} compiled with 40 checked array accesses", flush=True)
        return str(base), record

    with ThreadPoolExecutor(max_workers=args.jobs) as workers:
        records = dict(workers.map(check, controls))
    if args.link.read_bytes() != data:
        raise ValueError("production link changed during fixed-array builds")
    (args.output / "manifest.json").write_text(json.dumps(records, sort_keys=True, indent=2) + "\n")


if __name__ == "__main__":
    main()
