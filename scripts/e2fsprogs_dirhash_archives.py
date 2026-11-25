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
from check_e2fsprogs_utf8_trie import compile_trie


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


def prior_stage(record, name):
    parent = record.copy()
    layer = parent.pop(name)
    parent["candidate_sha256"] = layer["parent_archive_sha256"]
    parent["compiler_sources_sha256"] = layer["parent_sources_sha256"]
    return parent


def build(link, base, pinned=None, repository=ROOT, hangul_parent=None, trie_parent=None):
    with tempfile.TemporaryDirectory() as tmp:
        scratch = Path(tmp)
        if trie_parent is None:
            record = compile_candidate(link, base, scratch, hangul_parent)
        else:
            record = compile_trie(link, base, scratch, trie_parent)
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
    if (len(records) != len(CONSUMERS) or records.keys() != controls
            or {Path(name).parent.name for name in controls} != set(CONSUMERS)):
        raise ValueError("directory hash manifest must cover the release's 13 staged engines")

    previous = records
    for stage, manifest_name in (("trie", "e2fsprogs-hangul-arrays.json"), ("hangul", "e2fsprogs-dirhash-arrays.json")):
        if any(stage in row for row in previous.values()):
            pinned = json.loads((repository / "batches" / manifest_name).read_bytes())
            if any(stage not in row for row in previous.values()):
                raise ValueError(f"incomplete {stage} archive selection")
            previous = {name: prior_stage(row, stage) for name, row in previous.items()}
            if previous != pinned:
                raise ValueError(f"{stage} archive parents differ from {manifest_name}")

    def verify(item):
        name, record = item
        base = Path(name)
        target = repository / validate(link, base, record)
        if not target.is_file():
            build(link, base, pinned=record, repository=repository,
                  hangul_parent=prior_stage(record, "hangul") if "hangul" in record and "trie" not in record else None,
                  trie_parent=prior_stage(record, "trie") if "trie" in record else None)
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
    stage = parser.add_mutually_exclusive_group()
    stage.add_argument("--trie", action="store_true", help="add checked trie traversal to the Hangul release")
    stage.add_argument("--hangul", action="store_true", help="add Hangul decomposition to the current directory hash release")
    args = parser.parse_args()
    if args.jobs < 1:
        parser.error("--jobs must be positive")
    data = args.link.read_bytes()
    release = json.loads(data)
    parents = release.get("e2fsprogs_dirhash_arrays", {}) if args.hangul or args.trie else {}
    if args.hangul and (not parents or any("hangul" in record for record in parents.values())):
        parser.error("use the link report from the directory hash release preceding the Hangul conversion")
    if args.trie and (not parents or any("hangul" not in row or "trie" in row for row in parents.values())):
        parser.error("use a Hangul release link from before the trie conversion")
    link = control_view(release)
    controls = sorted(Path(name) for name in link["linked_private_inline_proofs"]
                      if Path(name).parent.parent.name == "rustbox-e2fsprogs-shared")
    if sorted(base.parent.name for base in controls) != sorted(CONSUMERS):
        raise ValueError("expected each of the shared-checksum engines exactly once")
    args.output.mkdir()

    def check(base):
        record = build(link, base, hangul_parent=parents[str(base)] if args.hangul else None,
                       trie_parent=parents[str(base)] if args.trie else None)
        (args.output / (base.parent.name + ".json")).write_text(json.dumps(record, sort_keys=True) + "\n")
        print(f"{base.parent.name} compiled and matched its control", flush=True)
        return str(base), record

    with ThreadPoolExecutor(max_workers=args.jobs) as workers:
        records = dict(workers.map(check, controls))
    if args.link.read_bytes() != data:
        raise ValueError("production link changed during fixed-array builds")
    (args.output / "manifest.json").write_text(json.dumps(records, sort_keys=True, indent=2) + "\n")


if __name__ == "__main__":
    main()
