#!/usr/bin/env python3
"""Measure all six rebuilt errno archives against their common base and prepared source inputs."""
# SPDX-License-Identifier: 0BSD
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from audit_linked_pointers import METRICS, measure
from build_checked_errno import substitute
from cargo_source_parent import cargo_origin
from check_cargo_private_inlines import ROOT, digest
from check_e2fsprogs_dirhash_arrays import source_list_digest


def count(data):
    return Counter({name: len(rx.findall(data)) for name, rx in METRICS.items()})


def compare(base_path, parent_path, pilots):
    base_raw, parent_raw = base_path.read_bytes(), parent_path.read_bytes()
    base, parent = json.loads(base_raw), json.loads(parent_raw)
    expected = json.loads((ROOT / "evidence/errno-composed-source-counts.json").read_bytes())
    if (base["binary"]["sha256"] != parent["binary"]["sha256"]
            or sha256(parent_raw).hexdigest() != expected["prepared_link_sha256"]
            or set(pilots) != set(expected["packages"])):
        raise ValueError("different base ELF, selected compiler inputs or set of packages")
    result = {}
    for name, pilot in pilots.items():
        row = json.loads((pilot / "pilot.json").read_bytes())
        key = row["archive"]
        native = parent["native_c_strings"][key]
        facts = expected["packages"][name]
        if (row["control_binary_sha256"] != base["binary"]["sha256"] or row["control_sha256"] != base["source_library_sha256"][key]
                or row["control_sha256"] != parent["source_library_sha256"][key] or row["archive"] != facts["archive"]
                or digest(pilot / Path(key).name) != row["candidate_sha256"] or digest(ROOT / key) != row["control_sha256"]):
            raise ValueError("unexpected compiled errno archive")
        previous = measure(base, archive_pair=(cargo_origin(base, key), Path(key)))["all"]
        sources, prepared = {}, Counter()
        with TemporaryDirectory() as tmp:
            crate = Path(tmp)
            def visit(archive, module, checksum, data):
                path = crate / module
                if str(archive) != key or str(module) in sources:
                    raise ValueError("unexpected compiler input")
                sources[str(module)] = checksum.hex()
                prepared.update(count(data))
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            measure(parent, inspect_module=visit, archive_pair=(cargo_origin(parent, key), Path(key)))
            changes, verified = substitute(crate, sources)
            final = prepared.copy()
            hashes = sources.copy()
            for mod, data in changes.items():
                final.subtract(count((crate / mod).read_bytes()))
                final.update(count(data))
                hashes[mod] = sha256(data).hexdigest()
        net = prepared["raw_pointer_type_tokens"] - final["raw_pointer_type_tokens"]
        if (any(row[k] != v for k, v in verified.items()) or len(sources) != previous["files"]
                or len(sources) != row["compiler_selected_sources"] or source_list_digest(sources) != native["candidate_sources_sha256"]
                or source_list_digest(sources) != row["parent_sources_sha256"] or source_list_digest(hashes) != row["candidate_sources_sha256"]
                or net != row["raw_pointer_types_removed"] or net != facts["raw_pointer_types_removed"]):
            raise ValueError("measured source changes differ from the compiled archive")
        result[name] = dict(archive=key, candidate_sha256=row["candidate_sha256"], compiler_inputs=len(sources),
                            base={k:previous[k] for k in METRICS}, prepared=prepared, candidate=final,
                            value_reads=row["value_reads"], value_writes=row["value_writes"], errno_types_removed=net,
                            total_types_removed=previous["raw_pointer_type_tokens"] - final["raw_pointer_type_tokens"])
    if base_path.read_bytes() != base_raw or parent_path.read_bytes() != parent_raw:
        raise ValueError("link changed during the inventory")
    return dict(base_link_sha256=sha256(base_raw).hexdigest(), prepared_link_sha256=sha256(parent_raw).hexdigest(),
                packages=result, totals={k:sum(r[k] for r in result.values()) for k in
                                          ("compiler_inputs", "errno_types_removed", "total_types_removed", "value_reads", "value_writes")})


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for arg in ("base", "parent"):
        p.add_argument(arg, type=Path)
    names = ("gawk", "grep", "gzip", "sed", "findutils", "shadow")
    for name in names:
        p.add_argument("--" + name, type=Path, required=True)
    a = p.parse_args()
    print(json.dumps(compare(a.base, a.parent, {n:getattr(a,n) for n in names}), indent=2, sort_keys=True))
