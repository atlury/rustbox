#!/usr/bin/env python3
"""Measure byte-identical preparation and live parser rewrites separately on the actual compiled sources."""
# SPDX-License-Identifier: GPL-3.0-or-later
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from audit_linked_pointers import METRICS, measure
from cargo_source_parent import cargo_origin
from check_cargo_private_inlines import ROOT, digest
from check_e2fsprogs_dirhash_arrays import source_list_digest
import build_curl_checked_parsers as curl
import build_less_message_catalog as less
import build_zstd_lorem as zstd

PACKAGES = {"curl": (curl.substitute, [curl.month.MODULE, curl.ftp.MODULE]),
            "less": (less.substitute, [less.MODULE]), "zstd": (zstd.substitute, [zstd.MODULE])}


def counts(data):
    return Counter({name: len(regex.findall(data)) for name, regex in METRICS.items()})


def compare(package, base_file, selected_file, pilot):
    row = json.loads((pilot / "pilot.json").read_bytes())
    key = row["archive"]
    archive = Path(key)
    base, selected = (json.loads(path.read_bytes()) for path in (base_file, selected_file))
    if (base["binary"]["sha256"] != selected["binary"]["sha256"] or selected["binary"]["sha256"] != row["control_binary_sha256"]
            or any(link["source_library_sha256"].get(key) != row["control_sha256"] for link in (base, selected))
            or digest(ROOT / archive) != row["control_sha256"] or digest(pilot / archive.name) != row["candidate_sha256"]):
        raise ValueError("expected the same linked archive before the live parser substitution")
    replace, modules = PACKAGES[package]
    base_counts = measure(base, archive_pair=(cargo_origin(base, key), archive))["all"]
    sources, selected_counts = {}, Counter()
    with TemporaryDirectory() as tmp:
        crate = Path(tmp)
        def capture(actual, module, checksum, data):
            if actual != archive or str(module) in sources:
                raise ValueError("unexpected or repeated compiler input")
            sources[str(module)] = checksum.hex()
            selected_counts.update(counts(data))
            if str(module) in modules:
                dest = crate / module
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(data)
        measure(selected, inspect_module=capture, archive_pair=(cargo_origin(selected, key), archive))
        edited, facts = replace(crate, sources)
        if set(edited) != set(modules) or any(row[k] != v for k, v in facts.items()):
            raise ValueError("parser substitution differs from its compiled receipt")
        actual_counts = selected_counts.copy()
        hashes = sources.copy()
        for module, data in edited.items():
            actual_counts.subtract(counts((crate / module).read_bytes()))
            actual_counts.update(counts(data))
            hashes[module] = sha256(data).hexdigest()
    if (len(sources) != row["compiler_selected_sources"] or source_list_digest(sources) != row["parent_sources_sha256"]
            or source_list_digest(hashes) != row["candidate_sources_sha256"] or base_counts["files"] != len(sources)
            or selected_counts["raw_pointer_type_tokens"] - actual_counts["raw_pointer_type_tokens"] != row["raw_pointer_types_removed"]):
        raise ValueError("compiler input, output, or measured inventory differs")
    return dict(archive=key, archive_sha256=row["candidate_sha256"], pilot_sha256=digest(pilot / "pilot.json"),
                base_link_sha256=digest(base_file), selected_link_sha256=digest(selected_file), compiler_inputs=len(sources),
                base={k: base_counts[k] for k in METRICS}, prepared=selected_counts, candidate=actual_counts,
                preparation_types_removed=base_counts["raw_pointer_type_tokens"] - selected_counts["raw_pointer_type_tokens"],
                parser_types_removed=row["raw_pointer_types_removed"],
                total_types_removed=base_counts["raw_pointer_type_tokens"] - actual_counts["raw_pointer_type_tokens"])


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("package", choices=PACKAGES)
    for name in ("base", "selected", "pilot"):
        p.add_argument(name, type=Path)
    a = p.parse_args()
    print(json.dumps(compare(a.package, a.base, a.selected, a.pilot), sort_keys=True, indent=2))
