#!/usr/bin/env python3
"""Combine disjoint type and foreign-declaration removals inside the same cold-built Cargo archive."""
# SPDX-License-Identifier: GPL-3.0-or-later
import argparse
import fcntl
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from build_checked_errno import replay
from build_current_foreign_declarations import apply_spans
from build_unused_c_types import substitute as unused_types
from cargo_archive_pilot import compile_mounted_sources, stage_selected_archive
from check_cargo_private_inlines import digest
from check_e2fsprogs_dirhash_arrays import source_list_digest
from prune_private_inlines import POINTER

MARKER = ".rustbox-stacked-declarations"
INPUTS = ".rustbox-stacked-inputs.json"


def source_digest(sources, changes):
    return source_list_digest({**sources, **{name: sha256(buf).hexdigest() for name, buf in changes.items()}})


def transform(crate, sources, types, foreign, tool=None):
    if (not (types["parent_sources_sha256"] == foreign["parent_sources_sha256"] == source_list_digest(sources))
            or types["archive"] != foreign["archive"]
            or not (types["control_sha256"] == foreign["control_sha256"] == foreign["candidate_sha256"])):
        raise ValueError("both cold builds must start from the same compiler inputs and archive")
    modified, type_facts = unused_types(crate, sources, tool)
    erased, foreign_facts = apply_spans(crate, sources, foreign["ranges"])
    for pilot, changes, facts in ((types, modified, type_facts), (foreign, erased, foreign_facts)):
        if (source_digest(sources, changes) != pilot["candidate_sources_sha256"]
                or any(value != pilot[key] for key, value in facts.items())):
            raise ValueError("independent source reconstruction differs from the original cold build")
    for module, spans in foreign["ranges"].items():
        if module not in modified:
            modified[module] = erased[module]
            continue
        original = (crate / module).read_bytes()
        merged = bytearray(modified[module])
        for start, end in spans:
            if merged[start:end] != original[start:end]:
                raise ValueError(f"overlapping removals in {module}")
            merged[start:end] = erased[module][start:end]
        modified[module] = bytes(merged)
    removed = sum(len(POINTER.findall((crate / m).read_bytes())) - len(POINTER.findall(data))
                  for m, data in modified.items())
    if removed != types["raw_pointer_types_removed"] + foreign["raw_pointer_types_removed"]:
        raise ValueError("independent pointer recount differs from the disjoint edits")
    return modified, dict(raw_pointer_types_removed=removed, unused_types=types, foreign_declarations=foreign)


def build(link, types, foreign, archive, output):
    if types["archive"] != archive or foreign["archive"] != archive:
        raise ValueError("compiler receipts belong to a different archive")

    def prepare(crate):
        path = crate / INPUTS
        with path.open("x") as stream:
            json.dump([types, foreign], stream)

    def verify(directory):
        replay(link, archive, directory, transform=lambda crate, sources: transform(crate, sources, types, foreign))
        if digest(directory / Path(archive).name) != types["candidate_sha256"]:
            raise ValueError("stacked archive differs from the archive used in the tested executable")

    with output.with_name(output.name + ".build.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if output.exists():
            verify(output)
            return
        with TemporaryDirectory(dir=output.parent) as tmp:
            stage = Path(tmp) / "archive"
            stage_selected_archive(link, stage, archive, MARKER, Path(__file__).name, prepare_crate=prepare,
                                   linux_scratch=True)
            verify(stage)
            stage.rename(output)


def build_all(link, types, foreign, output):
    output.mkdir(parents=True, exist_ok=True)
    results = {}
    control = digest(link)
    for key in sorted(types.keys() & foreign.keys()):
        first, second = types[key]["pilot"], foreign[key]["pilot"]
        if first["parent_sources_sha256"] != second["parent_sources_sha256"]:
            results[key] = {"status": "different compiler inputs"}
            continue
        identity = json.dumps([control, key, first, second], sort_keys=True).encode()
        directory = output / sha256(identity).hexdigest()
        build(link, first, second, key, directory)
        results[key] = dict(status="verified", directory=str(directory), pilot_sha256=digest(directory / "pilot.json"))
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mounted", type=Path)
    parser.add_argument("--link", type=Path)
    parser.add_argument("--types", type=Path)
    parser.add_argument("--foreign", type=Path)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--archive")
    group.add_argument("--all", action="store_true", help="process all archives shared by both selections")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.mounted:
        def mounted(crate, sources):
            return transform(crate, sources, *json.loads((crate / INPUTS).read_bytes()))
        compile_mounted_sources(args.mounted, mounted, MARKER, allow_identical=False)
    elif all((args.link, args.types, args.foreign, args.output)) and (args.archive or args.all):
        types, foreign = (json.loads(path.read_bytes())["archives"] for path in (args.types, args.foreign))
        if args.all:
            print(json.dumps(build_all(args.link, types, foreign, args.output), sort_keys=True, indent=2))
        else:
            build(args.link, types[args.archive]["pilot"], foreign[args.archive]["pilot"], args.archive, args.output)
    else:
        parser.error("supply the control, both compiler selections, an archive or --all, and the output")
