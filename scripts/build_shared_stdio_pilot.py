#!/usr/bin/env python3
"""Cold-build a selected Cargo archive before and after sharing identical glibc FILE layouts."""
# SPDX-License-Identifier: GPL-3.0-or-later
import argparse
import json
from pathlib import Path

from cargo_archive_pilot import compile_mounted_sources, stage_selected_archive
from check_cargo_private_inlines import LINK_REPORT
from share_stdio_layout import GZIP_OWNER, eligible, provider_namespace, share

MARKER = ".rustbox-stdio-layout-pilot"


def substitute(crate, sources):
    matched = sorted(Path(name) for name in sources if eligible((crate / name).read_bytes()))
    if len(matched) < 2:
        raise ValueError("expected two compiler-selected copies of the canonical FILE layout")
    owner = GZIP_OWNER if GZIP_OWNER in matched else matched[0]
    namespace = provider_namespace(crate / "lib.rs", owner)
    selection = crate / ".rustbox-stdio-modules.json"
    if selection.is_file():
        names = json.loads(selection.read_bytes())
        available = {str(module) for module in matched if module != owner}
        if not names or len(names) != len(set(names)) or not set(names) <= available:
            raise ValueError("requested modules lie outside the checked stdio family")
        matched = sorted(Path(name) for name in names)
    replacements = {}
    for module in matched:
        name = str(module)
        if module == owner:
            continue
        data = (crate / name).read_bytes()
        candidate = share(data, namespace)
        if candidate != data:
            replacements[name] = candidate
    return replacements, {"provider": str(owner), **({"provider_namespace": str(namespace)} if namespace != owner else {}), "reexporting_modules": sorted(replacements),
                          "raw_pointer_types_removed": 18 * len(replacements)}


def build(link_file, out, archive=None, modules=None):
    raw = link_file.read_bytes()
    link = json.loads(raw)
    if archive is None:
        key, = (k for k in link["source_library_sha256"] if k.endswith("/libgzip_1_14_reachable_audit.a"))
    else:
        key = str(archive)
    def selection(crate):
        subset = crate / ".rustbox-stdio-modules.json"
        if subset.exists():
            raise ValueError("unexpected stdio module selection in generated source")
        if modules is not None:
            subset.write_text(json.dumps(modules))
    stage_selected_archive(link_file, out, key, MARKER, Path(__file__).name, selection, omit_layer="shared_stdio_layouts")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--link", type=Path, default=LINK_REPORT)
    parser.add_argument("--archive", type=Path, help="original Cargo archive path from the link report (defaults to gzip)")
    opt = parser.add_mutually_exclusive_group(required=True)
    opt.add_argument("--output", type=Path)
    opt.add_argument("--mounted", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.mounted:
        compile_mounted_sources(args.mounted, substitute, MARKER, allow_identical=True)
    else:
        build(args.link, args.output.resolve(), args.archive)
