#!/usr/bin/env python3
"""Use the checked glibc byte functions in pkgconf's argument splitter and package-file parser."""
# SPDX-License-Identifier: ISC
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import re

from build_checked_errno import replay
from cargo_archive_pilot import compile_mounted_sources, stage_selected_archive
from check_cargo_private_inlines import ROOT, digest
from prune_private_inlines import POINTER
from rank_ctype_bytes import DECL, HELPER, matches, selected_helper

MARKER = ".rustbox-pkgconf-byte-classification"
SOURCE = ROOT / "work/upstream/pkgconf-3.0.11/libpkgconf"
REVIEWED = {
    "argvsplit": "34a2d11c489030592a3bac07ba03cec903a1d1ba1c28de7e439c187b6a29ba5b",
    "parser": "27b9772e65ae48f17f6df0b32123856054ecdcbdc728e468dda4bc26ffb7026e",
}
BYTE_TEST = re.compile(rb"\bis(space|alpha|digit)\(\s*\(unsigned char\)\s*(\*\w+)\s*\)")


def prepare(path):
    link = json.loads(path.read_bytes())
    key, = [k for k in link["source_library_sha256"] if Path(k).name.startswith("libpkgconf_") and k.endswith(".a")]
    pilot = json.loads((ROOT / "evidence/remaining-utility-native-c-strings.json").read_bytes())["verified"][key]
    if (link["source_library_sha256"][key] != pilot["control_sha256"] or pilot["candidate_sha256"] != pilot["control_sha256"]
            or key not in link.get("shared_stdio_layouts", {}) or key in link.get("native_c_strings", {})):
        raise ValueError("expected the pkgconf stdio parent before native strings")
    link["native_c_strings"] = {**link.get("native_c_strings", {}), key:pilot}
    return link


def substitute(crate, sources):
    changed, by_file = {}, {}
    flags = set()
    release = json.loads((ROOT / "evidence/remaining-utility-native-c-strings.json").read_bytes())
    key, = [k for k in release["verified"] if Path(k).name.startswith("libpkgconf_")]
    from check_e2fsprogs_dirhash_arrays import source_list_digest
    if source_list_digest(sources) != release["verified"][key]["candidate_sources_sha256"]:
        raise ValueError("pkgconf native C strings differ")
    for name, expected in REVIEWED.items():
        module = "src/libpkgconf/" + name + ".rs"
        data = (crate / module).read_bytes()
        canonical = (SOURCE / (name + ".c")).read_bytes()
        uses = matches(data)
        native = BYTE_TEST.findall(canonical)
        translated = [(m["flag"], m["value"]) for m in uses]
        if (sha256(data).hexdigest() != expected or sources[module] != expected or native != translated
                or len(uses) != (1 if name == "argvsplit" else 8) or data.count(DECL) != 1
                or data.count(b"__ctype_b_loc") != len(uses) + 1):
            raise ValueError("reviewed C and Rust byte tests differ in " + name)
        for m in reversed(uses):
            op = b"crate::rustbox_ctype::" + m["flag"] + b"(" + m["value"] + b" as u8)"
            data = data[:m.start()] + op + b"\n" * m[0].count(b"\n") + data[m.end():]
        data = data.replace(DECL, b"")
        changed[module] = data
        flags.update(flag.decode() for flag, _ in native)
        by_file[module] = dict(canonical_sha256=sha256(canonical).hexdigest(), old_sha256=expected,
                               new_sha256=sha256(data).hexdigest(), tests=dict(Counter(flag.decode() for flag, _ in native)))
    lib = (crate / "lib.rs").read_bytes()
    if b"rustbox_ctype" in lib:
        raise ValueError("crate already defines the classification interface")
    changed["lib.rs"] = lib + b"\n" + selected_helper(*sorted(flags))
    removed = sum(len(POINTER.findall((crate / k).read_bytes())) - len(POINTER.findall(v)) for k,v in changed.items())
    if removed != 4:
        raise ValueError("unexpected pkgconf pointer count")
    return changed, dict(modules=by_file, raw_pointer_types_removed=removed, ctype_table_reads_removed=9, helper_sha256=digest(HELPER))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--link", type=Path)
    p.add_argument("--prepare-parent", type=Path)
    p.add_argument("--mounted", type=Path)
    p.add_argument("--replay", action="store_true")
    p.add_argument("--output", type=Path)
    a = p.parse_args()
    if a.mounted:
        compile_mounted_sources(a.mounted, substitute, MARKER, allow_identical=True)
    elif a.prepare_parent:
        print(json.dumps(prepare(a.prepare_parent), sort_keys=True, indent=2))
    elif a.link:
        key, = [k for k in json.loads(a.link.read_bytes())["source_library_sha256"] if Path(k).name.startswith("libpkgconf_") and k.endswith(".a")]
        if a.replay:
            print(json.dumps(replay(a.link, key, a.output, transform=substitute), sort_keys=True, indent=2))
        elif a.output:
            stage_selected_archive(a.link, a.output, key, MARKER, Path(__file__).name)
        else:
            p.error("select a cold build or a source replay")
    else:
        p.error("supply a parent link")
