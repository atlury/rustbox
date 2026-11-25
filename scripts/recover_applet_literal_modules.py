#!/usr/bin/env python3
"""Retry a differing Coreutils or util-linux archive using changed applet entry sections as a hint."""
# SPDX-License-Identifier: GPL-3.0-or-later
import argparse
import json
from pathlib import Path
import re
import subprocess

from build_c_string_literal_pilot import build
from check_cargo_private_inlines import ROOT, digest
from verify_c_string_sources import verify


ENTRY_SECTION = {
    "coreutils-9.12": ".text.single_binary_main_{}",
    "util-linux-2.42.4": ".text.rustbox_{}_main",
}


def entry_bytes(archive, modules, template):
    names = {template.format(Path(m).stem): m for m in modules}
    if len(names) != len(modules):
        raise ValueError("ambiguous applet module stems")
    flags = [arg for name in sorted(names) for arg in ("-j", name)]
    process = subprocess.run(["objdump", "-s", *flags, archive], capture_output=True, check=True)
    found = {}
    current = None
    for line in process.stdout.decode("ascii", errors="replace").splitlines():
        if line.startswith("Contents of section ") and line.endswith(":"):
            current = names.get(line[len("Contents of section "):-1])
            if current in found:
                raise ValueError(f"duplicate entry section for {current}")
            if current is not None:
                found[current] = []
        elif current is not None:
            if re.match(r"^\s*[0-9a-fA-F]+\s+[0-9a-fA-F]{2}", line):
                found[current].append(line)
            else:
                current = None
    if not found or not all(found.values()):
        raise ValueError("objdump did not return the expected GNU applet entry bytes")
    return found


def recover(link, whole, out):
    row = json.loads((whole / "pilot.json").read_bytes())
    archive = Path(row["archive"])
    candidate = whole / archive.name
    template = ENTRY_SECTION.get(archive.parts[2])
    if (template is None or row["candidate_sha256"] == row["control_sha256"]
            or digest(candidate) != row["candidate_sha256"] or digest(ROOT / archive) != row["control_sha256"]):
        raise ValueError("expected a differing Coreutils or util-linux archive")
    verify(link, whole)
    left, right = [entry_bytes(path, row["modules"], template) for path in (ROOT / archive, candidate)]
    changed = sorted(m for m in left.keys() | right.keys() if left.get(m) != right.get(m))
    remaining = sorted(row["modules"].keys() - set(changed))
    if not changed or not remaining:
        raise ValueError(f"no independently testable split for changed entry modules {changed}")
    build(link, out, archive, modules=remaining)
    tested = json.loads((out / "pilot.json").read_bytes())
    if (tested["modules"] != {m: row["modules"][m] for m in remaining}
            or any(tested[k] != row[k] for k in ("archive", "control_sha256", "parent_sources_sha256"))
            or digest(out / archive.name) != tested["candidate_sha256"]):
        raise ValueError("subset differs from its selected parent or whole-archive conversions")
    verify(link, out)
    result = dict(archive=str(archive), whole_candidate_sha256=row["candidate_sha256"],
                  excluded_entry_modules=changed, candidate=tested,
                  byte_identical=tested["candidate_sha256"] == tested["control_sha256"])
    (out / "comparison.json").write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("link", "whole", "output"):
        parser.add_argument(arg, type=Path)
    args = parser.parse_args()
    recover(args.link, args.whole, args.output)
