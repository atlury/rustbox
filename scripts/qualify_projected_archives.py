#!/usr/bin/env python3
"""Replay compatible archive-local compiler selections on one physically tested Linux executable."""
# SPDX-License-Identifier: GPL-3.0-or-later
import argparse
from pathlib import Path
from tempfile import TemporaryDirectory

from verify_unused_type_rebase import LAYERS, ROOT, check_edge, digest, plan, read, write_result


def ancestry(start, target):
    """Return the audited source-only changes connecting two complete release reports."""
    if start == target:
        return []
    receipts = {}
    for path in (ROOT / "evidence").glob("dsfield-pointer-rollup-[0-9]*.json"):
        report = read(path)
        receipts[report["candidate_link_sha256"]] = (path, report["parent_link_sha256"])
    edges = []
    current = digest(target)
    stop = digest(start)
    seen = set()
    while current != stop:
        if current in seen or current not in receipts:
            raise ValueError("source controls have no verified common chain")
        seen.add(current)
        receipt, current = receipts[current]
        child = ROOT / "work/analysis" / receipt.stem / "release.json"
        edges.append((child, receipt))
    edges.reverse()
    parent = start
    for child, receipt in edges:
        check_edge(parent, child, receipt, {})
        parent = child
    if digest(parent) != digest(target):
        raise ValueError("unexpected final source control")
    return edges


def checked_executable(link, selection, evidence, elf):
    release, selected, tested = read(link), read(selection), read(evidence)
    inputs = selected["archives"]
    comparison, commands = tested["link"], tested["commands"]
    if (not inputs or digest(link) != selected["parent_link_sha256"]
            or digest(link) != comparison["parent_link_report_sha256"]
            or not (digest(selection) == tested["selection_sha256"] == comparison["selection_sha256"]
                    == commands["selection_sha256"])
            or not (release["binary"]["sha256"] == selected["parent_binary_sha256"] == comparison["parent"]["sha256"])
            or not (digest(elf) == comparison["candidate"]["sha256"] == commands["binary_sha256"])
            or commands["side"] != "candidate" or selected["counts"] != tested["counts"]):
        raise ValueError("qualified command evidence does not identify the requested executable")
    for side, field in (("parent", "control_sha256"), ("candidate", "candidate_sha256")):
        hashes = {key: row["pilot"][field] for key, row in inputs.items()}
        if comparison[side]["archive_sha256"] != hashes:
            raise ValueError(f"{side} link used different archive inputs")
    suites = commands["suites"]
    if (not suites or any(s["passed"] <= 0 for s in suites.values())
            or sum(s["passed"] for s in suites.values()) != commands["comparisons"]):
        raise ValueError("inconsistent canonical command totals")
    return inputs, commands


def qualify(link, selection, evidence, elf, foreign_link, foreign_selection, foreign_evidence, latest, *, stacked=(), export=None):
    replaced, commands = checked_executable(link, selection, evidence, elf)
    foreign, witness = read(foreign_selection), read(foreign_evidence)
    if (digest(foreign_link) != foreign["parent_link_sha256"]
            or digest(foreign_selection) != witness["compiler_selection_sha256"]
            or not (witness["binary_sha256"] == foreign["parent_binary_sha256"] == read(foreign_link)["binary"]["sha256"])
            or foreign["counts"] != witness["counts"]):
        raise ValueError("foreign compiler selection does not match its control")
    edges = ancestry(foreign_link, link) + ancestry(link, latest)
    identical = {key: row for key, row in foreign["archives"].items() if key not in replaced}
    # All source layers of an individual archive come from the same cold build.
    # Other archives retain every byte-identical improvement in the latest control.
    projected = read(latest)
    for parent, chosen in ((read(link), replaced), (read(foreign_link), identical)):
        for layer in LAYERS:
            for key in chosen:
                if key in parent.get(layer, {}):
                    projected.setdefault(layer, {})[key] = parent[layer][key]
                elif layer in projected:
                    projected[layer].pop(key, None)
    merged = dict(replaced)
    stacked_receipts = {}
    for directory in stacked:
        path = directory / "pilot.json"
        row = read(path)
        key = row["archive"]
        if (key in stacked_receipts or key not in replaced or key not in foreign["archives"]
                or row["unused_types"] != replaced[key]["pilot"]
                or row["foreign_declarations"] != foreign["archives"][key]["pilot"]
                or row["candidate_sha256"] != replaced[key]["pilot"]["candidate_sha256"]):
            raise ValueError("stacked edits do not reproduce the archive used by the tested executable")
        relative = directory.resolve().relative_to(ROOT).as_posix()
        merged[key] = dict(directory=relative, pilot=row)
        stacked_receipts[key] = dict(directory=relative, pilot_sha256=digest(path),
                                    candidate_sources_sha256=row["candidate_sources_sha256"],
                                    removed=row["raw_pointer_types_removed"])
    with TemporaryDirectory() as tmp:
        control = Path(tmp) / "release.json"
        write_result(control, projected)
        rebuilt = [ROOT / row["directory"] for row in merged.values()]
        same = [ROOT / row["directory"] for row in identical.values()]
        combined = plan(control, rebuilt, extra_foreign=same)
    if combined["archives"] != {**merged, **identical}:
        raise ValueError("cold build receipts differ from projected compiler inputs")
    if export is not None:
        # Publish the release and its matching selection together only after replay.
        if export.exists():
            raise FileExistsError(export)
        with TemporaryDirectory(dir=export.parent) as tmp:
            stage = Path(tmp) / "export"
            stage.mkdir()
            write_result(stage / "release.json", projected)
            if digest(stage / "release.json") != combined["parent_link_sha256"]:
                raise ValueError("exported release differs from the compiler control")
            write_result(stage / "selection.json", combined)
            stage.rename(export)
    return dict(counts=combined["counts"], projected_control_sha256=combined["parent_link_sha256"],
                candidate_binary_sha256=commands["binary_sha256"], canonical_comparisons=commands["comparisons"],
                tested_selection_sha256=digest(selection), tested_link_evidence_sha256=digest(evidence),
                foreign_selection_sha256=digest(foreign_selection), foreign_evidence_sha256=digest(foreign_evidence),
                latest_control_sha256=digest(latest), foreign_control_sha256=digest(foreign_link),
                tested_control_sha256=digest(link), source_only_chain={p.name: digest(p) for _, p in edges},
                rebuilt_archives=sorted(replaced), identical_foreign_archives=sorted(identical),
                stacked_archives=stacked_receipts,
                deferred_overlaps=sorted((replaced.keys() & foreign["archives"].keys()) - stacked_receipts.keys()))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("link", "selection", "evidence", "elf", "foreign_link", "foreign_selection",
                 "foreign_evidence", "latest", "output"):
        parser.add_argument(name, type=Path)
    parser.add_argument("--stacked", type=Path, action="append", default=[], metavar="COLD_BUILD")
    parser.add_argument("--export", type=Path, help="publish reproducible release and selection files in a new directory")
    args = vars(parser.parse_args())
    output = args.pop("output")
    write_result(output, qualify(**args))
