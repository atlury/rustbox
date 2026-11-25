#!/usr/bin/env python3
"""Replay the native C string and errno transformations together on the selected compiler sources."""
# SPDX-License-Identifier: 0BSD
import argparse
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from build_checked_errno import replay
from check_cargo_private_inlines import ROOT

# Each record is from a complete cold build whose archive matched its parent.
SELECTORS = {
    "gawk": ("remaining-utility-native-c-strings.json", "verified"),
    "grep": ("mixed-array-c-string-utilities.json", "identical"),
    "sed": ("mixed-array-c-string-utilities.json", "identical"),
    "gzip": ("gzip-composed-stdio-c-strings.json", None),
    "shadow": ("mixed-array-c-string-legacy.json", "identical"),
    "findutils": ("mixed-array-c-string-utilities.json", "identical"),
}


def prepare(source, packages):
    raw = source.read_bytes()
    link = json.loads(raw)
    parents = dict(link.get("native_c_strings", {}))
    selected = {}
    for package in packages:
        prefix = "lib" + package + "_"
        key, = [k for k in link["source_library_sha256"] if Path(k).name.startswith(prefix) and k.endswith(".a")]
        if package == "gzip":
            # gzip's 240 literals were rebuilt after the shared stdio layout.
            row = json.loads((ROOT / "work/analysis/gzip-composed-c-strings/pilot.json").read_bytes())
            qualified = json.loads((ROOT / "evidence/gzip-composed-stdio-c-strings.json").read_bytes())
            if any(qualified.get(k) != v for k, v in row.items()):
                raise ValueError("gzip differs from its qualified composed source")
        else:
            evidence, field = SELECTORS[package]
            row = json.loads((ROOT / "evidence" / evidence).read_bytes())[field][key]
        expected = link["source_library_sha256"][key]
        if (row["archive"] != key or row["control_sha256"] != expected or row["candidate_sha256"] != expected
                or key in parents and parents[key] != row):
            raise ValueError(f"native C strings differ from the selected {package} build")
        parents[key] = row
        selected[key] = row
    link["native_c_strings"] = parents
    payload = (json.dumps(link, indent=2, sort_keys=True) + "\n").encode()
    with TemporaryDirectory() as tmp:
        staged = Path(tmp) / "link.json"
        staged.write_bytes(payload)
        rows = {key: replay(staged, key) for key in selected}
    for key, row in rows.items():
        if (row["parent_sources_sha256"] != selected[key]["candidate_sources_sha256"]
                or row["compiler_selected_sources"] != selected[key]["compiler_selected_sources"]):
            raise ValueError(f"compiler input selection differs for {key}")
    if source.read_bytes() != raw:
        raise ValueError("parent link changed during replay")
    return payload, dict(parent_link_sha256=sha256(raw).hexdigest(), prepared_link_sha256=sha256(payload).hexdigest(),
                         archives=rows)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("parent", type=Path)
    p.add_argument("output", type=Path)
    p.add_argument("packages", choices=SELECTORS, nargs="+")
    a = p.parse_args()
    if len(set(a.packages)) != len(a.packages):
        p.error("duplicate package")
    payload, report = prepare(a.parent, a.packages)
    with a.output.open("xb") as f:
        f.write(payload)
    print(json.dumps(report, indent=2, sort_keys=True))
