#!/usr/bin/env python3
"""Replace the six portable E2fsprogs bitops entry points on their selected compiler inputs."""
# SPDX-License-Identifier: LGPL-2.0-only
import argparse
from hashlib import sha256
import json
from pathlib import Path
import re

from check_cargo_private_inlines import ROOT, digest
from direct_source_pair import build_pair, direct_receipt, mounted_pair
from prune_private_inlines import POINTER

SOURCE = ROOT / "work/upstream/e2fsprogs-1.47.4/lib/ext2fs/bitops.c"
HELPER = ROOT / "compat/e2fsprogs/bitmap_bits.rs"
FUNCTIONS = {
    "ext2fs_set_bit": "0d2f510e1e92da14bf86eae79fbdc836c32dc8369712f7b0d21411ba17a89797",
    "ext2fs_clear_bit": "862614131cd969285407f0f757d1ec6a944bafeb31ca2e7fd6c489ddbbfb251a",
    "ext2fs_test_bit": "f1d39e33609518a552d210d0d4b35952c270f1789585b6bf3c73973a2e4c3163",
    "ext2fs_set_bit64": "d3de01cda47bc2f5f012e6ab3ac43fe34f9f08831ed5f84853eb416cf5b7309e",
    "ext2fs_clear_bit64": "91944a10fdf2c4ff070fac52c49f09418dbe6da46a00dbba3e0358a5f9f603a5",
    "ext2fs_test_bit64": "ebdb374ff3890d731614dceaa2ca7a2b6ca9d228ecf47f504bc689ffd5e1c2f1",
}
ENTRY = re.compile(rb'(?ms)^#\[no_mangle\]\npub unsafe extern "C" fn (ext2fs_(?:set|clear|test)_bit(?:64)?)\(.*?^\}')


def transform(data):
    if digest(SOURCE) != "6be65f6d560afa9849a99dc11c5ca490fe1089002c2416bb6874a3a6b589d8fa":
        raise ValueError("canonical E2fsprogs bitops.c changed")
    matches = list(ENTRY.finditer(data))
    if (len(matches) != len(FUNCTIONS) or b"mod bitmap_byte" in data
            or {m[1].decode(): sha256(m[0]).hexdigest() for m in matches} != FUNCTIONS):
        raise ValueError("expected the six qualified E2fsprogs bitmap definitions")
    helper = HELPER.read_bytes()
    result = ENTRY.sub(lambda m: helper if m.start() == matches[0].start() else b"", data)
    return result, dict(canonical_sha256=digest(SOURCE), helper_sha256=sha256(helper).hexdigest(),
                        control_module_sha256=sha256(data).hexdigest(), candidate_module_sha256=sha256(result).hexdigest(),
                        raw_pointer_types_removed=len(POINTER.findall(data))-len(POINTER.findall(result)))


def substitute(crate, sources):
    module, = [m for m in sources if m.endswith("/lib/ext2fs/bitops.rs")]
    data = (crate / module).read_bytes()
    if sha256(data).hexdigest() != sources[module]:
        raise ValueError("E2fsprogs bitmap module differs from its compiler input")
    new, facts = transform(data)
    return {module: new}, dict(facts, module=module)


def build(link, archive, output):
    build_pair(link, output, archive, Path(__file__).name, ["--mounted", archive], substitute)


def inventory(link):
    from audit_linked_pointers import measure

    raw = link.read_bytes()
    release = json.loads(raw)
    archives = {}
    def inspect(archive, module, checksum, source):
        if not str(module).endswith("/lib/ext2fs/bitops.rs"):
            return
        key = str(archive)
        if key in archives or sha256(source).digest() != checksum:
            raise ValueError("duplicate bitmap module or stale compiler input")
        _, facts = transform(source)
        archives[key] = dict(facts, module=str(module), archive_sha256=release["source_library_sha256"][key])
    measure(release, inspect_module=inspect)
    if not archives or raw != link.read_bytes():
        raise ValueError("empty bitmap inventory or changed release")
    return dict(archives=archives, link_sha256=sha256(raw).hexdigest(), binary_sha256=release["binary"]["sha256"],
                source_pointer_types_removed=sum(row["raw_pointer_types_removed"] for row in archives.values()))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mounted")
    p.add_argument("--link", type=Path)
    p.add_argument("--archive")
    p.add_argument("--output", type=Path)
    p.add_argument("--replay", action="store_true")
    p.add_argument("--inventory", action="store_true", help="replay all selected bitmap modules without compiling")
    a = p.parse_args()
    if a.mounted:
        mounted_pair(Path("/trial/release.json"), Path("/trial/result"), a.mounted, substitute, allow_identical=True)
    elif a.inventory and a.link:
        print(json.dumps(inventory(a.link), indent=2, sort_keys=True))
    elif a.link and a.archive and a.output:
        if a.replay:
            row = direct_receipt(a.link, a.archive, substitute)
            row["candidate_sha256"] = digest(a.output / Path(a.archive).name)
            if row != json.loads((a.output / "pilot.json").read_bytes()):
                raise ValueError("archive or compiler source replay changed")
            print(json.dumps(row, sort_keys=True))
        else:
            build(a.link, a.archive, a.output)
    else:
        p.error("supply the link, archive, and pilot output")
