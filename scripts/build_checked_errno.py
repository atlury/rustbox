#!/usr/bin/env python3
"""Reduce glibc errno access to a per-crate value interface in eligible generated modules."""
# SPDX-License-Identifier: 0BSD
import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

from cargo_archive_pilot import compile_mounted_sources, stage_selected_archive
from cargo_source_parent import cargo_origin
from check_cargo_private_inlines import ROOT, digest
from prune_private_inlines import POINTER
from verify_c_string_sources import syntax_tool

MARKER = ".rustbox-checked-errno"
HELPER = ROOT / "compat/linux/errno.rs"
SCANNER = ROOT / "tools/private-inlines/src/bin/errno-values.rs"


def substitute(crate, sources):
    if "lib.rs" not in sources:
        raise ValueError("expected an existing compiled crate root")
    rows = json.loads(subprocess.check_output([syntax_tool("errno-values"), crate], input=json.dumps(sorted(sources)).encode()))
    if not rows or "lib.rs" in rows:
        raise ValueError("expected eligible leaf modules")
    if any(b"rustbox_errno" in (crate / path).read_bytes() for path in sources):
        raise ValueError("errno accessor name already used")
    changed = {"lib.rs": (crate / "lib.rs").read_bytes() + b"\n" + HELPER.read_bytes()}
    reads = writes = 0
    for module, (gets, sets, edits) in rows.items():
        data = (crate / module).read_bytes()
        if sha256(data).hexdigest() != sources[module]:
            raise ValueError("unexpected errno compiler input")
        for start, end, text in reversed(edits):
            data = data[:start] + text.encode() + b"\n" * data[start:end].count(b"\n") + data[end:]
        if b"__errno_location" in data:
            raise ValueError("errno address still referenced in selected module")
        changed[module] = data
        reads += gets
        writes += sets
    reduction = sum(len(POINTER.findall((crate / n).read_bytes())) - len(POINTER.findall(b)) for n, b in changed.items())
    if reduction != len(rows) - 1:
        raise ValueError("expected exactly one remaining declaration in place of the selected copies")
    return changed, dict(modules={m: row[:2] for m, row in rows.items()}, value_reads=reads, value_writes=writes,
                         raw_pointer_types_removed=reduction, helper_sha256=digest(HELPER), scanner_sha256=digest(SCANNER))


def replay(link, key, pilot=None):
    from audit_linked_pointers import measure
    from check_e2fsprogs_dirhash_arrays import source_list_digest
    base = json.loads(link.read_bytes())
    sources = {}
    with TemporaryDirectory() as tmp:
        crate = Path(tmp)
        def capture(archive, module, checksum, data):
            if str(archive) != key or str(module) in sources:
                raise ValueError("unexpected compiler input")
            dest = crate / module
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            sources[str(module)] = checksum.hex()
        origin = cargo_origin(base, key)
        measure(base, inspect_module=capture, archive_pair=(origin, Path(key)))
        changes, facts = substitute(crate, sources)
    result = dict(**facts, compiler_selected_sources=len(sources), parent_sources_sha256=source_list_digest(sources),
                  candidate_sources_sha256=source_list_digest({**sources, **{k: sha256(v).hexdigest() for k,v in changes.items()}}),
                  archive=key, control_sha256=digest(ROOT / key), control_binary_sha256=base["binary"]["sha256"])
    if str(origin) != key:
        result["cargo_archive"] = str(origin)
    if pilot is not None:
        result["candidate_sha256"] = digest(pilot / Path(key).name)
        if result != json.loads((pilot / "pilot.json").read_bytes()):
            raise ValueError("archive receipt differs from the independently reproduced source selection")
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--link", type=Path)
    p.add_argument("--archive")
    p.add_argument("--replay", action="store_true")
    p.add_argument("--output", type=Path)
    p.add_argument("--mounted", type=Path)
    args = p.parse_args()
    if args.mounted:
        compile_mounted_sources(args.mounted, substitute, MARKER, allow_identical=True)
    elif args.replay and args.link and args.archive:
        print(json.dumps(replay(args.link, args.archive, args.output), indent=2, sort_keys=True))
    elif args.link and args.archive and args.output:
        stage_selected_archive(args.link, args.output, args.archive, MARKER, Path(__file__).name)
    else:
        p.error("supply the link, archive and either --replay or --output")
