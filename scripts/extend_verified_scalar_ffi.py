#!/usr/bin/env python3
"""Refresh a broader ABI sweep on the current compiler sources and retain every qualified default import."""
# SPDX-License-Identifier: 0BSD
import argparse
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from audit_linked_pointers import check_identical_layer, measure
from build_scalar_ffi import check_extension
from check_cargo_private_inlines import digest
from prepare_identical_archives import prepare, validate_link
from refresh_pointer_selections import refresh

FIELD = "shared_scalar_ffi"


def extend(link, active, broader, output, workspace, jobs):
    raw = link.read_bytes()
    before = json.loads(raw)
    old = json.loads(active.read_bytes())
    if validate_link(old, before["source_library_sha256"], before, FIELD) != before[FIELD]:
        raise ValueError("existing manifest does not match the current release")
    sources = {k:v for k,v in before.items() if k != FIELD}
    workspace.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=workspace) as tmp:
        base = Path(tmp) / "parent.json"
        base.write_text(json.dumps(sources, indent=2, sort_keys=True)+"\n")
        renewed = Path(tmp) / "refreshed.json"
        report = refresh(base, broader, renewed, workspace/"cold-builds", FIELD, jobs)
        proposed = json.loads(renewed.read_bytes())
    chosen = dict(old)
    for key, item in proposed.items():
        if key in old:
            prior = old[key]["pilot"]
            if item["pilot"]["raw_pointer_types_removed"] <= prior["raw_pointer_types_removed"]:
                continue
            check_extension(prior, item["pilot"])
        chosen[key] = item
    prepare(chosen, FIELD)
    rows = validate_link(chosen, sources["source_library_sha256"], sources, FIELD)
    after = {**sources, FIELD: rows}
    counts = measure(before)
    updated = measure(after)
    if before[FIELD] != rows:
        check_identical_layer(before,after,counts,updated,FIELD)
    if raw != link.read_bytes():
        raise ValueError("release changed during the extension")
    with TemporaryDirectory(dir=output.parent) as tmp:
        staged=Path(tmp)/"manifest.json"
        staged.write_text(json.dumps(chosen,indent=2,sort_keys=True)+"\n")
        staged.replace(output)
    return dict(parent_link_sha256=sha256(raw).hexdigest(),manifest_sha256=digest(output),
                previous=len(old), selected=len(chosen), refresh=report, counts={
                    group:{"before":counts[group]["raw_pointer_type_tokens"],"after":updated[group]["raw_pointer_type_tokens"]}
                    for group in ("all","counting_identical_files_once")})


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("link","active","broader","output","workspace"):
        p.add_argument(name,type=Path)
    p.add_argument("--jobs",type=int,default=2)
    args = p.parse_args()
    if args.jobs < 1 or args.output.resolve() in {p.resolve() for p in (args.link,args.active,args.broader)}:
        p.error("expected positive jobs and a separate output manifest")
    print(json.dumps(extend(args.link,args.active,args.broader,args.output,args.workspace,args.jobs),indent=2,sort_keys=True))
