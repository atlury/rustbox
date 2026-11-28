#!/usr/bin/env python3
"""Compile device-group lookups with the release bridge engine's direct rustc recipe."""
# SPDX-License-Identifier: GPL-2.0-or-later
import json
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory

from build_checked_errno import replay
from build_group_names import substitute
from build_iproute2_bridge_address_protocols import BRIDGE
from build_staged_c_strings import publish
from cargo_source_parent import cargo_origin
from check_cargo_private_inlines import ROOT, digest
from check_e2fsprogs_dirhash_arrays import compile_staged
from e2fsprogs_foreign_declarations import staged_compiler_inputs
from iproute2_address_protocol_archive import control_view


def bridge_receipt(link, key, transform=substitute):
    row = replay(link, key, transform=transform)
    if row.pop("cargo_archive") != str(BRIDGE):
        raise ValueError("unexpected bridge source origin")
    return dict(row, rustc_archive=str(BRIDGE))


def mounted(link, output, key):
    release = json.loads(link.read_bytes())
    expected = release["source_library_sha256"][key]
    if cargo_origin(release, key) != BRIDGE or not output.is_dir() or any(output.iterdir()):
        raise ValueError("expected the selected bridge archive and an empty result directory")
    with TemporaryDirectory() as tmp:
        scratch = Path(tmp)
        crate, inputs, compiler = staged_compiler_inputs(control_view(release), BRIDGE, scratch)
        archive = scratch / BRIDGE.name

        def compile_pair(captured, sources):
            if inputs != sources.keys():
                raise ValueError("direct bridge and captured compiler inputs differ")
            for name, checksum in sources.items():
                shutil.copyfile(captured / name, crate / name)
                if digest(crate / name) != checksum:
                    raise ValueError(f"captured bridge source differs for {name}")
            if compile_staged(crate, inputs, compiler, archive) != expected:
                raise ValueError("cold bridge control differs from the release archive")
            replacements, facts = substitute(crate, sources)
            for name, data in replacements.items():
                (crate / name).write_bytes(data)
            candidate = compile_staged(crate, inputs, compiler, archive)
            if candidate == expected:
                raise ValueError("expected a changed live device-group reader")
            shutil.copyfile(archive, output / archive.name)
            if digest(output / archive.name) != candidate:
                raise ValueError("device-group archive copy changed")
            return replacements, facts

        row = bridge_receipt(link, key, compile_pair)
        row["candidate_sha256"] = digest(output / BRIDGE.name)
        (output / "pilot.json").write_text(json.dumps(row, indent=2, sort_keys=True) + "\n")


def build(link, output, key):
    output = output.resolve()
    raw = link.read_bytes()
    if output.exists():
        raise FileExistsError(output)
    with TemporaryDirectory(dir=output.parent) as tmp:
        stage = Path(tmp)
        (stage / "release.json").write_bytes(raw)
        result = stage / "result"
        result.mkdir()
        subprocess.run(["docker","run","--rm","--network","none","--platform","linux/amd64",
                        "-v",f"{ROOT}:/work:ro","-v",f"{stage}:/trial","rustbox-e2fsprogs:2026-11-24",
                        "python3","-B","/work/scripts/build_group_names_bridge.py",key],check=True)
        row = bridge_receipt(link, key)
        row["candidate_sha256"] = digest(result / BRIDGE.name)
        if raw != link.read_bytes() or row != json.loads((result / "pilot.json").read_bytes()):
            raise ValueError("bridge archive or independent source replay differs")
        publish(result, output, BRIDGE.name)


if __name__ == "__main__":
    key, = sys.argv[1:]
    mounted(Path("/trial/release.json"), Path("/trial/result"), key)
