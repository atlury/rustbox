#!/usr/bin/env python3
"""Recompute unused C layout types after compiler-confirmed foreign declarations have been removed."""
# SPDX-License-Identifier: GPL-3.0-or-later
import argparse
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from build_checked_errno import replay
from build_current_foreign_declarations import apply_spans
from build_unused_c_types import substitute as unused_types
from cargo_archive_pilot import compile_mounted_sources, stage_selected_archive
from cargo_source_parent import cargo_origin, direct_crate
from check_cargo_private_inlines import ROOT, digest
from check_e2fsprogs_dirhash_arrays import source_list_digest
from direct_source_pair import build_pair, direct_receipt, mounted_pair
from prune_private_inlines import POINTER
from qualify_iproute2_combined_names import write_result

MARKER = ".rustbox-cascaded-declarations"
INPUT = ".rustbox-cascaded-input.json"


class NoAdditionalLayouts(ValueError):
    pass


def transform(crate, sources, foreign, tool=None):
    if (foreign["parent_sources_sha256"] != source_list_digest(sources)
            or foreign["candidate_sha256"] != foreign["control_sha256"]):
        raise ValueError("expected the exact compiler inputs for a byte-identical foreign declaration cleanup")
    changed, facts = apply_spans(crate, sources, foreign["ranges"])
    if any(foreign[key] != value for key, value in facts.items()):
        raise ValueError("foreign declarations differ from verified scanner results")
    intermediate = dict(sources)
    with TemporaryDirectory() as tmp:
        view = Path(tmp)
        for name, original in sources.items():
            src, dst = crate / name, view / name
            if Path(name).is_absolute() or ".." in Path(name).parts or digest(src) != original:
                raise ValueError("unexpected module in selected compiler inputs")
            dst.parent.mkdir(parents=True, exist_ok=True)
            if name in changed:
                dst.write_bytes(changed[name])
                intermediate[name] = sha256(changed[name]).hexdigest()
            else:
                dst.write_bytes(src.read_bytes())
        if source_list_digest(intermediate) != foreign["candidate_sources_sha256"]:
            raise ValueError("first transformation differs from the cold foreign-declaration build")
        layouts, after = unused_types(view, intermediate, tool)
        changed.update(layouts)
    total = sum(len(POINTER.findall((crate / m).read_bytes())) - len(POINTER.findall(data)) for m, data in changed.items())
    if total != facts["raw_pointer_types_removed"] + after["raw_pointer_types_removed"]:
        raise ValueError("combined pointer inventory differs from ordered edits")
    if after["raw_pointer_types_removed"] == 0:
        raise NoAdditionalLayouts("no verified additional pointer reduction after the foreign cleanup")
    return changed, dict(foreign_declarations=foreign, unused_after_foreign=after, raw_pointer_types_removed=total)


def selection(manifest, key):
    row = json.loads(manifest.read_bytes())["archives"][key]["pilot"]
    if row["archive"] != key:
        raise ValueError("foreign compiler receipt belongs to a different archive")
    return row


def trial(link, manifest, key, output=None):
    foreign = selection(manifest, key)
    release = json.loads(link.read_bytes())
    if release["source_library_sha256"][key] != foreign["control_sha256"]:
        raise ValueError("foreign declaration receipt belongs to a different linked archive")
    apply = lambda crate, sources: transform(crate, sources, foreign)
    direct = direct_crate(cargo_origin(release, key)) is not None
    if output is None:
        return direct_receipt(link, key, apply) if direct else replay(link, key, transform=apply)
    if direct:
        mounted = Path("/work") / manifest.resolve().relative_to(ROOT)
        build_pair(link, output, key, Path(__file__).name, ["--direct", key, "--foreign", mounted], apply)
    else:
        def prepare(crate):
            with (crate / INPUT).open("x") as stream:
                json.dump(foreign, stream)
        stage_selected_archive(link, output, key, MARKER, Path(__file__).name, prepare_crate=prepare,
                               linux_scratch=True)
        replay(link, key, output, transform=apply)
    return json.loads((output / "pilot.json").read_bytes())


def rank(link, manifest, jobs):
    control, pinned = digest(link), digest(manifest)
    archives = json.loads(manifest.read_bytes())["archives"]
    def one(key):
        try:
            row = trial(link, manifest, key)
        except NoAdditionalLayouts:
            return key, dict(additional_layout_pointers=0)
        return key, dict(additional_layout_pointers=row["unused_after_foreign"]["raw_pointer_types_removed"],
                         combined_pointers=row["raw_pointer_types_removed"],
                         parent_sources_sha256=row["parent_sources_sha256"],
                         candidate_sources_sha256=row["candidate_sources_sha256"])
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        rows = dict(pool.map(one, sorted(archives)))
    if digest(link) != control or digest(manifest) != pinned:
        raise ValueError("compiler selection changed during ranking")
    return dict(control_sha256=control, foreign_selection_sha256=pinned, archives=rows,
                additional_layout_pointers=sum(row["additional_layout_pointers"] for row in rows.values()))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mounted", type=Path)
    parser.add_argument("--direct")
    parser.add_argument("--link", type=Path)
    parser.add_argument("--foreign", type=Path)
    parser.add_argument("--archive")
    parser.add_argument("--rank", action="store_true", help="rank additional layouts on every archive in the foreign selection")
    parser.add_argument("--jobs", type=int, default=1)
    parser.add_argument("--output", type=Path, help="cold build in a new directory (omit for a source-only trial)")
    args = parser.parse_args()
    if args.mounted:
        def mounted(crate, sources):
            return transform(crate, sources, json.loads((crate / INPUT).read_bytes()))
        compile_mounted_sources(args.mounted, mounted, MARKER, allow_identical=True)
    elif args.direct and args.foreign:
        row = selection(args.foreign, args.direct)
        mounted_pair(Path("/trial/release.json"), Path("/trial/result"), args.direct,
                     lambda crate, sources: transform(crate, sources, row), allow_identical=True)
    elif args.rank and args.link and args.foreign and args.output and args.jobs > 0:
        write_result(args.output, rank(args.link, args.foreign, args.jobs))
    elif args.link and args.foreign and args.archive:
        print(json.dumps(trial(args.link, args.foreign, args.archive, args.output), sort_keys=True))
    else:
        parser.error("supply the control, foreign compiler selection and archive")
