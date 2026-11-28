#!/usr/bin/env python3
"""Cold-build the GNU tar exclusion and argument tables in one archive."""
# SPDX-License-Identifier: GPL-3.0-or-later
from hashlib import sha256
from pathlib import Path

from build_tar_argmatch_tables import substitute as option_tables
from build_tar_exclusion_tables import substitute as exclusions
from prune_private_inlines import POINTER
from tar_table_pilot import main

MARKER = ".rustbox-combined-tar-name-tables"


def substitute(crate, sources):
    replacements = {}
    members = {}
    for name, change in (("exclusion", exclusions), ("argmatch", option_tables)):
        edits, facts = change(crate, sources)
        if replacements.keys() & edits.keys():
            raise ValueError("GNU tar table rewrites overlap")
        for module in edits:
            if sha256((crate / module).read_bytes()).hexdigest() != sources[module]:
                raise ValueError(f"GNU tar compiler source changed for {module}")
        members[name] = facts
        replacements.update(edits)
    removed = sum(len(POINTER.findall((crate / m).read_bytes())) - len(POINTER.findall(data))
                  for m, data in replacements.items())
    if removed != sum(row["raw_pointer_types_removed"] for row in members.values()):
        raise ValueError("combined raw-pointer count differs from the disjoint source edits")
    return replacements, dict(name_tables=members, raw_pointer_types_removed=removed)


if __name__ == "__main__":
    main(Path(__file__), MARKER, substitute)
