#!/usr/bin/env python3
"""Replace the two upstream xattr hash loops on verified compiler-selected inputs."""
# SPDX-License-Identifier: LGPL-2.0-only
import argparse
from hashlib import sha256
import json
from pathlib import Path
import re

from check_cargo_private_inlines import ROOT, digest
from direct_source_pair import build_pair, mounted_pair
from e2fsprogs_source_pair import inventory, selected_module
from prune_private_inlines import POINTER

MODULE = "/lib/ext2fs/ext_attr.rs"
SOURCE = ROOT / "work/upstream/e2fsprogs-1.47.4/lib/ext2fs/ext_attr.c"
HELPER = ROOT / "compat/e2fsprogs/xattr_hash.rs"
ENTRY = re.compile(rb'(?ms)^#\[no_mangle\]\npub unsafe extern "C" fn (ext2fs_ext_attr_hash_entry(?:_signed)?)\(.*?^\}')
DEFINITIONS = {
    b"ext2fs_ext_attr_hash_entry": "d3fb3a9486ac137ad623a3e08e210d95f82757e992846b5c2b896825207dc892",
    b"ext2fs_ext_attr_hash_entry_signed": "f324a57ac569c61cb8dfe98534c86a5d480e2ce4f1f61293b6728083052aef27",
}


def transform(source):
    canonical = digest(SOURCE)
    matches = list(ENTRY.finditer(source))
    if (digest(ROOT / "work/normalized/e2fsprogs-1.47.4/lib/ext2fs/ext_attr.c") != canonical
            or canonical != "8b875e69b1d277df0997159fb31130982e5e3fed517b9b6154544b1812276356"
            or len(matches) != 2 or {m[1]: sha256(m[0]).hexdigest() for m in matches} != DEFINITIONS
            or b"mod xattr_hash" in source or b"fn hash_xattr_entry" in source):
        raise ValueError("unrecognized canonical or translated E2fsprogs hash functions")
    helper = HELPER.read_bytes()
    result = ENTRY.sub(lambda m: helper if m.start() == matches[0].start() else b"", source)
    return result, dict(canonical_sha256=canonical, helper_sha256=sha256(helper).hexdigest(),
                        control_module_sha256=sha256(source).hexdigest(), candidate_module_sha256=sha256(result).hexdigest(),
                        raw_pointer_types_removed=len(POINTER.findall(source)) - len(POINTER.findall(result)))


def substitute(crate, sources):
    return selected_module(crate, sources, MODULE, transform)


def build(link, archive, output):
    build_pair(link, output, archive, Path(__file__).name, ["--mounted", archive], substitute)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mounted")
    parser.add_argument("--link", type=Path)
    parser.add_argument("--archive")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--inventory", action="store_true")
    a = parser.parse_args()
    if a.mounted:
        mounted_pair(Path("/trial/release.json"), Path("/trial/result"), a.mounted, substitute, allow_identical=True)
    elif a.link and a.inventory:
        print(json.dumps(inventory(a.link, MODULE, transform), sort_keys=True, indent=2))
    elif a.link and a.archive and a.output:
        build(a.link, a.archive, a.output)
    else:
        parser.error("supply --link with --inventory or with --archive and --output")
