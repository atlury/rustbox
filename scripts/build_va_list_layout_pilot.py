#!/usr/bin/env python3
"""Share the exact generated x86-64 System V va_list tag within one translated static archive."""
# SPDX-License-Identifier: GPL-3.0-or-later
import argparse
import json
from hashlib import sha256
from pathlib import Path
import re

from cargo_archive_pilot import compile_mounted_sources, stage_selected_archive
from share_stdio_layout import provider_namespace

TAG = b"""#[derive(Copy, Clone)]
#[repr(C)]
pub struct __va_list_tag {
    pub gp_offset: ::core::ffi::c_uint,
    pub fp_offset: ::core::ffi::c_uint,
    pub overflow_arg_area: *mut ::core::ffi::c_void,
    pub reg_save_area: *mut ::core::ffi::c_void,
}
"""
MARKER = ".rustbox-va-list-layout"


def substitute(crate, sources, read=None, *, modules=None):
    if read is None:
        read = lambda name: (crate / name).read_bytes()
    matches = []
    for name in sorted(sources):
        data = read(name)
        if data.count(TAG) == 1 and data.count(b"pub struct __va_list_tag {") == 1:
            matches.append(name)
    if len(matches) < 2:
        raise ValueError("expected duplicate copies of the pinned System V layout")
    owner = matches[0]
    namespace = provider_namespace(crate / "lib.rs", Path(owner))
    parts = namespace.with_suffix("").parts
    if namespace.suffix != ".rs" or not all(re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", p) for p in parts):
        raise ValueError("unrecognized provider module")
    alias = ("pub use crate::" + "::".join(parts) + "::__va_list_tag;").encode()
    alias += b"\n" * TAG.count(b"\n")
    selected = matches[1:]
    if modules is not None:
        if not modules or len(set(modules)) != len(modules) or not set(modules) <= set(selected):
            raise ValueError("requested variadic modules must be distinct matched consumers")
        selected = sorted(modules)
    changed = {name: read(name).replace(TAG, alias) for name in selected}
    return changed, dict(provider=owner, provider_namespace=str(namespace), reexporting_modules=selected,
                         declaration_sha256=sha256(TAG).hexdigest(), raw_pointer_types_removed=2 * len(changed))


def build(link, key, output, modules=None):
    from cargo_source_parent import cargo_origin, direct_crate
    if direct_crate(cargo_origin(json.loads(link.read_bytes()), key)) is not None:
        from build_staged_c_strings import build as direct
        direct(link, output, key, modules, va_list_layout=True)
    else:
        def select(crate):
            path = crate / ".rustbox-va-list-modules.json"
            if path.exists():
                raise ValueError("unexpected module selection in generated crate")
            if modules is not None:
                path.write_text(json.dumps(modules))
        stage_selected_archive(link, output, key, MARKER, Path(__file__).name, select)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--link", type=Path)
    p.add_argument("--archive")
    p.add_argument("--output", type=Path)
    p.add_argument("--mounted", type=Path)
    args = p.parse_args()
    if args.mounted:
        def selected(crate, sources):
            path = crate / ".rustbox-va-list-modules.json"
            return substitute(crate, sources, modules=json.loads(path.read_bytes()) if path.exists() else None)
        compile_mounted_sources(args.mounted, selected, MARKER, allow_identical=True)
    elif args.link and args.archive and args.output:
        build(args.link, args.archive, args.output)
    else:
        p.error("--link, --archive and --output are required")
