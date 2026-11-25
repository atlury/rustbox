#!/usr/bin/env python3
"""Keep GNU awk's integer-key classification byte-valued after native strings and errno."""
# SPDX-License-Identifier: 0BSD
import argparse
from hashlib import sha256
import json
from pathlib import Path

import build_checked_errno as errno
from cargo_archive_pilot import compile_mounted_sources, stage_selected_archive
from check_cargo_private_inlines import ROOT, digest
from check_e2fsprogs_dirhash_arrays import source_list_digest
from prune_private_inlines import POINTER
from rank_ctype_bytes import DECL, matches

MODULE = "src/int_array.rs"
CANONICAL = ROOT / "work/upstream/gawk-5.4.0/int_array.c"
HELPER = ROOT / "compat/linux/ctype.rs"
MARKER = ".rustbox-gawk-ctype"


def substitute(crate, sources):
    data = (crate / MODULE).read_bytes()
    proof = json.loads((ROOT / "evidence/errno-composed-source-counts.json").read_bytes())["packages"]["gawk"]
    if (sha256(data).hexdigest() != sources[MODULE] or sources[MODULE] != "d7abf277fa4dd71f18a9c306a8ed825855c6b98786e6d37deb3995e63436d8b9"
            or digest(CANONICAL) != "58ca0f6987a0dc6ea70d7718f780db5775774b41dd158e1060ec6ce39a6700f8"
            or b"(! isdigit((unsigned char) *cp) && *cp != '-')" not in CANONICAL.read_bytes()):
        raise ValueError("expected the reviewed GNU awk integer-key function")
    changed, details = errno.substitute(crate, sources)
    previous = {**sources, **{name: sha256(v).hexdigest() for name, v in changed.items()}}
    if source_list_digest(previous) != proof["candidate_sources_sha256"]:
        raise ValueError("GNU awk compiler sources differ after errno conversion")
    data = changed[MODULE]
    match, = matches(data)
    if match["value"] != b"*cp" or match["flag"] != b"digit" or data.count(b"__ctype_b_loc") != 2 or data.count(DECL) != 1:
        raise ValueError("expected one unsigned-byte digit lookup and its declaration")
    rewritten = b"crate::rustbox_ctype::digit(*cp as u8)"
    edit = data[:match.start()] + rewritten + b"\n" * match[0].count(b"\n") + data[match.end():]
    edited = edit.replace(DECL, b"")
    if b"__ctype_b_loc" in edited or len(POINTER.findall(data)) - len(POINTER.findall(edited)) != 2:
        raise ValueError("unexpected GNU awk pointer substitution")
    helper = HELPER.read_bytes()
    if digest(HELPER) != json.loads((ROOT / "evidence/glibc-ctype-values.json").read_bytes())["helper_sha256"]:
        raise ValueError("classification helper differs from the locale tests")
    # Only publish the one operation used in this compiled crate.
    helper = b"".join(line for line in helper.splitlines(keepends=True)
                      if b"classification!(" not in line or b"classification!(digit," in line)
    changed["lib.rs"] += b"\n" + helper
    changed[MODULE] = edited
    return changed, dict(errno=details, after_errno_sources_sha256=proof["candidate_sources_sha256"],
                         module=MODULE, canonical_sha256=digest(CANONICAL), helper_sha256=digest(HELPER),
                         module_after_errno_sha256=sha256(data).hexdigest(), candidate_module_sha256=sha256(edited).hexdigest(),
                         ctype_pointer_types_removed=2, ctype_table_reads_removed=1,
                         raw_pointer_types_removed=details["raw_pointer_types_removed"] + 2)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mounted", type=Path)
    p.add_argument("--link", type=Path)
    p.add_argument("--output", type=Path)
    p.add_argument("--replay", action="store_true")
    args = p.parse_args()
    if args.mounted:
        compile_mounted_sources(args.mounted, substitute, MARKER, allow_identical=True)
    elif args.link:
        keys = json.loads(args.link.read_bytes())["source_library_sha256"]
        key, = [k for k in keys if Path(k).name.startswith("libgawk_") and k.endswith(".a")]
        if args.replay:
            print(json.dumps(errno.replay(args.link, key, args.output, transform=substitute), sort_keys=True, indent=2))
        elif args.output:
            stage_selected_archive(args.link, args.output, key, MARKER, Path(__file__).name)
        else:
            p.error("supply --output for a cold build")
    else:
        p.error("supply a parent link")
