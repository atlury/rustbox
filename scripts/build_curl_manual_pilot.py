#!/usr/bin/env python3
"""Build and compare the current curl archive and its packed-manual candidate offline."""
# SPDX-License-Identifier: curl
import argparse
import json
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory

from audit_linked_pointers import measure
from cargo_archive_pilot import compile_mounted_archive
from check_cargo_private_inlines import ROOT, LINK_REPORT, digest, layout
from curl_manual import MODULE, replace_manual

MARKER = ".rustbox-curl-manual-pilot"


def build(link_path, output):
    if output.exists():
        raise ValueError("expected a new pilot directory")
    raw = link_path.read_bytes()
    from curl_manual_archive import pilot_parent_view
    link = pilot_parent_view(json.loads(raw))
    key, = (k for k in link["source_library_sha256"] if k.endswith("/libcurl_8_23_0_normalized_audit.a"))
    archive = Path(key)
    source, base = layout(archive)
    sha = link["source_library_sha256"][key]
    if digest(ROOT / archive) != sha:
        raise ValueError("curl archive does not match the selected multicall")
    selection = {"binary": link["binary"]}
    for field in ("source_library_sha256", "linked_private_inline_proofs", "linked_second_inline_proofs", "linked_foreign_declaration_proofs"):
        if key in link.get(field, {}):
            selection[field] = {key: link[field][key]}

    with TemporaryDirectory(dir=output.parent) as tmp:
        scratch = Path(tmp)
        crate = scratch / "source"
        target = scratch / "target"
        target.mkdir()
        shutil.copytree(ROOT / source, crate, ignore=shutil.ignore_patterns("target"))
        sources = {}

        def capture(selected, module, checksum, data):
            if selected != archive or str(module) in sources:
                raise ValueError("unexpected curl compiler input")
            path = crate / module
            if path.read_bytes() != data:
                path.write_bytes(data)
            sources[str(module)] = checksum.hex()

        measure(selection, inspect_module=capture)
        _, changes = replace_manual((crate / MODULE).read_bytes())
        if sources[str(MODULE)] != changes["control_module_sha256"]:
            raise ValueError("curl manual is missing from the selected compiler inputs")
        (crate / MARKER).write_text(sha)
        (target / "control.json").write_text(json.dumps(dict(archive=key, control_sha256=sha,
            control_binary_sha256=link["binary"]["sha256"], sources=sources)))
        subprocess.run(["docker", "run", "--rm", "--network", "none", "--platform", "linux/amd64",
                        "-v", f"{ROOT}:/work:ro", "--tmpfs", "/work/.git:ro",
                        "-v", f"{crate}:/work/{source}", "-v", f"{target}:/work/{base}",
                        "-v", "rustbox-pointer-cargo-registry:/root/.cargo/registry:ro",
                        "rustbox-e2fsprogs:2026-11-24", "python3", "-B",
                        "/work/scripts/build_curl_manual_pilot.py", "--mounted", key], check=True)
        row = json.loads((target / "pilot.json").read_bytes())
        candidate = target / "release" / archive.name
        if (any(row[k] != v for k, v in changes.items()) or digest(candidate) != row["candidate_sha256"]
                or row["control_sha256"] != sha or link_path.read_bytes() != raw):
            raise ValueError("curl candidate, pilot or source release changed")
        result = scratch / "result"
        result.mkdir()
        candidate.replace(result / archive.name)
        (target / "pilot.json").replace(result / "pilot.json")
        result.rename(output)
        print(json.dumps(row, sort_keys=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--link", type=Path, default=LINK_REPORT)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--output", type=Path)
    group.add_argument("--mounted", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.mounted:
        compile_mounted_archive(args.mounted, MODULE, replace_manual, MARKER)
    else:
        build(args.link, args.output.resolve())
