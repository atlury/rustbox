#!/usr/bin/env python3
"""Pack E2fsprogs' fixed error names while retaining its public C return and fallback-buffer lifetime."""
# SPDX-License-Identifier: LGPL-2.0-only
import argparse
from hashlib import sha256
import json
from pathlib import Path
import re

from build_checked_errno import replay
from check_cargo_private_inlines import ROOT, digest
from prune_private_inlines import POINTER

SOURCE = ROOT / "work/upstream/e2fsprogs-1.47.4/lib/e2p/errcode.c"
ENGINES = {"libdebugfs_audit.a", "libdumpe2fs_audit.a", "libtune2fs_audit.a"}
CANONICAL_SHA = "c0a5a9e6690e0686b2d06ea4960eadcebb89ee61c5a77c7df136b3fe8c1836a4"
MODULE_SHA = "327c5ab0234a8c08dacec443f35b4971d1b0ae015d71b1e5b7176d3949177a23"


def substitute(crate, sources):
    module, = [name for name in sources if name.endswith("/lib/e2p/errcode.rs")]
    data = (crate / module).read_bytes()
    if digest(SOURCE) != CANONICAL_SHA or sources[module] != MODULE_SHA or sha256(data).hexdigest() != MODULE_SHA:
        raise ValueError("unrecognized canonical error names or translated compiler input")

    entries = SOURCE.read_bytes().split(b"static const char *err_string[] = {\n", 1)[1].split(b"\n};", 1)[0]
    names = [re.fullmatch(rb'\s*"([A-Z]*)",\s*(?:/\*\s*\d+\s*\*/)?', line).group(1)
             for line in entries.splitlines()]
    start = data.index(b"static mut err_string:")
    end = data.index(b"\n];\n", start) + 4
    native = re.findall(rb'crate::rustbox_checked_c_str!\(b"([A-Z]*)\\0"\)\.as_ptr\(\)', data[start:end])
    if native != names or len(names) != 18 or len(set(names)) != len(names) or data.count(b"err_string") != 2:
        raise ValueError("translated indices differ from canonical error codes")

    offsets = []
    payload = bytearray()
    for name in names:
        offsets.append(len(payload))
        payload.extend(name + b"\0")
    if len(payload) > 256:
        raise ValueError("error-name bytes exceed a one-byte offset")
    table = (b'static ERROR_NAMES: &[u8] = b"' + bytes(payload).replace(b"\0", b"\\0") + b'";\n'
             + b"const ERROR_NAME_OFFSETS: [u8; 18] = [" + b", ".join(str(off).encode() for off in offsets) + b"];\n")
    read_start = data.index(b"    if (err as usize)", end)
    fallback = data.index(b"    sprintf(", read_start)
    replacement = (b"    if let Some(&start) = ERROR_NAME_OFFSETS.get(err as usize) {\n"
                   b"        return ERROR_NAMES[usize::from(start)..].as_ptr().cast();\n    }\n")
    result = data[:start] + table + data[end:read_start] + replacement + data[fallback:]
    return {module: result}, dict(module=module, canonical_sha256=CANONICAL_SHA, parent_module_sha256=MODULE_SHA,
                                  candidate_module_sha256=sha256(result).hexdigest(), static_pointer_slots_removed=len(names),
                                  table_bytes=len(payload), offset_bytes=len(offsets), table_sha256=sha256(payload).hexdigest(),
                                  raw_pointer_types_removed=len(POINTER.findall(data)) - len(POINTER.findall(result)))


def main():
    from build_staged_c_strings import build
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("link", type=Path)
    parser.add_argument("archive")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--replay", action="store_true")
    mode.add_argument("--build", type=Path)
    args = parser.parse_args()
    if Path(args.archive).name not in ENGINES or args.archive not in json.loads(args.link.read_bytes())["source_library_sha256"]:
        parser.error("expected one of the three linked E2fsprogs error-name consumers")
    if args.replay:
        print(json.dumps(replay(args.link, args.archive, transform=substitute), indent=2, sort_keys=True))
    else:
        build(args.link, args.build, args.archive, e2p_error_names=True)


if __name__ == "__main__":
    main()
