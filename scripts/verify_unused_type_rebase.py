#!/usr/bin/env python3
"""Verify that independently rebuilt, byte-identical archives preserve a tested batch link."""
# SPDX-License-Identifier: GPL-3.0-or-later
import argparse
import json
from pathlib import Path

from audit_linked_pointers import measure
from cargo_source_parent import cargo_origin
from check_cargo_private_inlines import ROOT, digest
from check_e2fsprogs_dirhash_arrays import source_list_digest
from extend_pointer_selection import LAYERS
from qualify_iproute2_combined_names import write_result
from qualify_unused_type_batch import plan


def read(path):
    return json.loads(path.read_bytes())


def check_edge(parent_link, next_link, rollup, reserved):
    parent, current, update = read(parent_link), read(next_link), read(rollup)
    if (update["parent_link_sha256"] != digest(parent_link) or update["candidate_link_sha256"] != digest(next_link)
            or update["binary_sha256"] != parent["binary"]["sha256"]):
        raise ValueError("archive-identical rollup does not connect these two releases")
    changed = {k for k in parent.keys() | current.keys() if parent.get(k) != current.get(k)}
    if (not changed or changed != set(update["layers"])
            or not changed <= LAYERS.keys()):
        raise ValueError("physical release or an unsupported source selection changed")
    inputs = current["source_library_sha256"]
    manifests = {v: ROOT / k for k, v in update["input_manifests"].items()}
    for layer in sorted(changed):
        checksum = update["layers"][layer]["manifest_sha256"]
        manifest = manifests[checksum]
        if digest(manifest) != checksum:
            raise ValueError("archive receipt manifest changed")
        receipts = read(manifest)
        old, new = parent.get(layer, {}), current[layer]
        keys = {k for k in old.keys() | new.keys() if old.get(k) != new.get(k)}
        if keys != set(update["layers"][layer]["archives"]) or keys.intersection(reserved):
            raise ValueError("unexpected or overlapping archive changes")
        for key in keys:
            receipt = new[key]
            if (receipts[key]["pilot"] != receipt or receipt["archive"] != key or receipt["control_sha256"] != inputs[key]
                    or receipt["candidate_sha256"] != inputs[key] or digest(ROOT / key) != inputs[key]):
                raise ValueError(f"archive {key} is not byte-identical to the linked input")


def verify(parent_link, next_link, rollup, selection, next_selection, linked_evidence, elf, *, through=()):
    parent, current = read(parent_link), read(next_link)
    update, previous, selected = read(rollup), read(selection), read(next_selection)
    tests = read(linked_evidence)
    if (digest(parent_link) != previous["parent_link_sha256"]
            or digest(next_link) != selected["parent_link_sha256"]
            or digest(next_link) != update["candidate_link_sha256"]
            or digest(selection) != tests["selection_sha256"]
            or digest(selection) != tests["link"]["selection_sha256"]
            or previous["archives"] != selected["archives"]):
        raise ValueError("link or compiler selection does not match the qualified batch")
    if (not previous["archives"] or previous["counts"] != tests["counts"]
            or tests["link"]["parent_link_report_sha256"] != digest(parent_link)
            or parent["binary"]["sha256"] != tests["link"]["parent"]["sha256"]
            or update["binary_sha256"] != parent["binary"]["sha256"]
            or digest(elf) != tests["commands"]["binary_sha256"]
            or tests["commands"]["binary_sha256"] != tests["link"]["candidate"]["sha256"]
            or tests["commands"]["selection_sha256"] != digest(selection)):
        raise ValueError("linked executable or command evidence differs")
    current_parent = parent_link
    census = {mode: row["before"] for mode, row in previous["counts"].items()}
    for target, witness in [*through, (next_link, rollup)]:
        check_edge(current_parent, target, witness, selected["archives"])
        edge_counts = read(witness)["counts"]
        if census != {mode: row["before"] for mode, row in edge_counts.items()}:
            raise ValueError("intermediate compiler counts do not connect")
        census = {mode: row["after"] for mode, row in edge_counts.items()}
        current_parent = target
    directories = [ROOT / row["directory"] for row in previous["archives"].values()]
    if plan(next_link, directories) != selected:
        raise ValueError("compiler replay differs from the supplied selection")
    for mode, counts in selected["counts"].items():
        if counts["before"] != update["counts"][mode]["after"]:
            raise ValueError("independent compiler census differs from the archive-identical rollup")
    return dict(binary_sha256=digest(elf), counts=selected["counts"],
                canonical_comparisons=tests["commands"]["comparisons"], linked_evidence_sha256=digest(linked_evidence),
                unchanged_archive_proof_sha256=digest(rollup), selection_sha256=digest(next_selection),
                original_link_sha256=digest(parent_link), candidate_control_link_sha256=digest(next_link),
                **({"intermediate_rollups": [{"link_sha256": digest(path), "proof_sha256": digest(proof)}
                                             for path, proof in through]} if through else {}))


def include_identical_foreign(proof, link, selection, foreign_selection, foreign_evidence):
    """Recount disjoint compiler changes on the same executable, including shared source hashes."""
    changed, foreign = read(selection), read(foreign_selection)
    receipt = read(foreign_evidence)
    if (proof["selection_sha256"] != digest(selection) or proof["counts"] != changed["counts"]
            or digest(link) != changed["parent_link_sha256"]
            or foreign["parent_link_sha256"] not in ({digest(link)} |
                {r["link_sha256"] for r in proof.get("intermediate_rollups", [])})
            or receipt["compiler_selection_sha256"] != digest(foreign_selection)
            or receipt["binary_sha256"] != changed["parent_binary_sha256"]
            or foreign["parent_binary_sha256"] != receipt["binary_sha256"] or receipt["counts"] != foreign["counts"]):
        raise ValueError("foreign declaration evidence belongs to a different release")
    replaced = changed["archives"]
    unchanged = {k: v for k, v in foreign["archives"].items() if k not in replaced}
    stale = {}
    if foreign["parent_link_sha256"] != digest(link):
        release = read(link)
        for key, record in list(unchanged.items()):
            sources = {}
            def capture(archive, module, checksum, data):
                if str(archive) != key or str(module) in sources:
                    raise ValueError("unexpected compiler input during compatibility check")
                sources[str(module)] = checksum.hex()
            measure(release, inspect_module=capture, archive_pair=(cargo_origin(release, key), Path(key)))
            observed = source_list_digest(sources)
            expected = record["pilot"]["parent_sources_sha256"]
            if observed != expected:
                stale[key] = dict(recorded_parent_sha256=expected, current_parent_sha256=observed)
                del unchanged[key]
    if not unchanged:
        raise ValueError("no foreign archive has compatible, disjoint compiler inputs")
    directories = [ROOT / row["directory"] for row in replaced.values()]
    extras = [ROOT / row["directory"] for row in unchanged.values()]
    combined = plan(link, directories, extra_foreign=extras)
    if combined["archives"] != {**replaced, **unchanged}:
        raise ValueError("fresh compiler receipts differ from the pinned selections")
    return dict(**{k: v for k, v in proof.items() if k != "counts"}, counts=combined["counts"],
                foreign_evidence_sha256=digest(foreign_evidence), foreign_selection_sha256=digest(foreign_selection),
                included_foreign_archives=sorted(unchanged), overlapping_archives=sorted(set(replaced) & set(foreign["archives"])),
                **({"requires_rebuild": stale} if stale else {}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("parent_link", "next_link", "rollup", "selection", "next_selection", "linked_evidence", "elf", "output"):
        parser.add_argument(name, type=Path)
    parser.add_argument("--through", type=Path, nargs=2, action="append", default=[], metavar=("LINK", "ROLLUP"))
    parser.add_argument("--include-foreign", type=Path, nargs=2, metavar=("SELECTION", "EVIDENCE"))
    args = vars(parser.parse_args())
    output = args.pop("output")
    foreign = args.pop("include_foreign")
    result = verify(**args)
    if foreign:
        result = include_identical_foreign(result, args["next_link"], args["next_selection"], *foreign)
    write_result(output, result)
