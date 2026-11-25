#!/usr/bin/env python3
"""Cold-build a selected Cargo archive before and after sharing identical glibc FILE layouts."""
# SPDX-License-Identifier: GPL-3.0-or-later
import argparse
import json
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory

from audit_linked_pointers import measure
from cargo_archive_pilot import compile_mounted_sources
from check_cargo_private_inlines import ROOT, LINK_REPORT, digest, layout
from share_stdio_layout import GZIP_OWNER, eligible, share

MARKER = ".rustbox-stdio-layout-pilot"


def substitute(crate, sources):
    matched = sorted(Path(name) for name in sources if eligible((crate / name).read_bytes()))
    if len(matched) < 2:
        raise ValueError("expected two compiler-selected copies of the canonical FILE layout")
    owner = GZIP_OWNER if GZIP_OWNER in matched else matched[0]
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
        candidate = share(data, owner)
        if candidate != data:
            replacements[name] = candidate
    return replacements, {"provider": str(owner), "reexporting_modules": sorted(replacements),
                          "raw_pointer_types_removed": 18 * len(replacements)}


def build(link_file, out, archive=None, modules=None):
    raw = link_file.read_bytes()
    link = json.loads(raw)
    if archive is None:
        key, = (k for k in link["source_library_sha256"] if k.endswith("/libgzip_1_14_reachable_audit.a"))
    else:
        key = str(archive)
    sha = link["source_library_sha256"][key]
    archive = Path(key)
    src, base = layout(archive)
    if out.exists() or digest(ROOT / archive) != sha:
        raise ValueError("expected an empty destination and the linked archive")
    receipts = {k: {key: link[k][key]} for k in ("source_library_sha256", "linked_private_inline_proofs",
                "linked_second_inline_proofs", "linked_foreign_declaration_proofs") if key in link.get(k, {})}
    with TemporaryDirectory(dir=out.parent) as tmp:
        crate, target, result = (Path(tmp) / n for n in ("crate", "target", "result"))
        shutil.copytree(ROOT / src, crate, ignore=shutil.ignore_patterns("target"))
        target.mkdir()
        subset = crate / ".rustbox-stdio-modules.json"
        if subset.exists():
            raise ValueError("unexpected stdio module selection in generated source")
        if modules is not None:
            subset.write_text(json.dumps(modules))
        sources = {}

        def capture(selected, module, checksum, data):
            if selected != archive or str(module) in sources:
                raise ValueError("unexpected archive compiler input")
            (crate / module).write_bytes(data)
            sources[str(module)] = checksum.hex()

        measure(dict(receipts, binary=link["binary"]), inspect_module=capture)
        (crate / MARKER).write_text(sha)
        (target / "control.json").write_text(json.dumps(dict(archive=key, control_sha256=sha,
            control_binary_sha256=link["binary"]["sha256"], sources=sources)))
        subprocess.run(["docker", "run", "--rm", "--network", "none", "--platform", "linux/amd64",
                        "-v", f"{ROOT}:/work:ro", "--tmpfs", "/work/.git:ro",
                        "-v", f"{crate}:/work/{src}", "-v", f"{target}:/work/{base}",
                        "-v", "rustbox-pointer-cargo-registry:/root/.cargo/registry:ro",
                        "rustbox-e2fsprogs:2026-11-24", "python3", "-B",
                        "/work/scripts/build_shared_stdio_pilot.py", "--mounted", key], check=True)
        row = json.loads((target / "pilot.json").read_bytes())
        candidate = target / "release" / archive.name
        if digest(candidate) != row["candidate_sha256"] or row["control_sha256"] != sha or link_file.read_bytes() != raw:
            raise ValueError("archive or selected release changed during the experiment")
        result.mkdir()
        candidate.replace(result / archive.name)
        (target / "pilot.json").replace(result / "pilot.json")
        result.rename(out)
        print(json.dumps(row, sort_keys=True))


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
