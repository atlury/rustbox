#!/usr/bin/env python3
"""Cold-build substitutions against the selected sources of a direct-rustc archive."""
# SPDX-License-Identifier: GPL-2.0-or-later
import json
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory

from build_checked_errno import replay
from build_staged_c_strings import publish
from cargo_source_parent import cargo_origin, direct_crate
from check_cargo_private_inlines import ROOT, digest
from check_e2fsprogs_dirhash_arrays import compile_staged
from e2fsprogs_foreign_declarations import staged_compiler_inputs
from iproute2_address_protocol_archive import control_view as iproute2_control
from e2fsprogs_dirhash_archives import control_view as e2fsprogs_control
from curl_manual_archive import parent_view as curl_control


def direct_receipt(link, key, transform):
    origin = cargo_origin(json.loads(link.read_bytes()), key)
    if direct_crate(origin) is None:
        raise ValueError("expected a direct-rustc archive")
    row = replay(link, key, transform=transform)
    if row.pop("cargo_archive", key) != str(origin):
        raise ValueError("direct source origin differs from the linked archive")
    return dict(row, rustc_archive=str(origin))


def mounted_pair(link, output, key, substitute, *, allow_identical):
    release = json.loads(link.read_bytes())
    expected = release["source_library_sha256"][key]
    origin = cargo_origin(release, key)
    if direct_crate(origin) is None or not output.is_dir() or any(output.iterdir()):
        raise ValueError("expected a direct engine and an empty result directory")
    parent = iproute2_control(e2fsprogs_control(curl_control(release)))
    with TemporaryDirectory() as tmp:
        scratch = Path(tmp)
        crate, inputs, compiler = staged_compiler_inputs(parent, origin, scratch)
        archive = scratch / origin.name

        def compile_pair(captured, sources):
            if inputs != sources.keys():
                raise ValueError("direct recipe and captured compiler inputs differ")
            for name, checksum in sources.items():
                shutil.copyfile(captured / name, crate / name)
                if digest(crate / name) != checksum:
                    raise ValueError(f"captured engine source differs for {name}")
            if compile_staged(crate, inputs, compiler, archive) != expected:
                raise ValueError("cold direct control differs from the release archive")
            replacements, facts = substitute(crate, sources)
            for name, data in replacements.items():
                (crate / name).write_bytes(data)
            candidate = compile_staged(crate, inputs, compiler, archive)
            if not allow_identical and candidate == expected:
                raise ValueError("expected a changed direct archive")
            shutil.copyfile(archive, output / archive.name)
            if digest(output / archive.name) != candidate:
                raise ValueError("direct archive copy changed")
            return replacements, facts

        row = direct_receipt(link, key, compile_pair)
        row["candidate_sha256"] = digest(output / origin.name)
        (output / "pilot.json").write_text(json.dumps(row, indent=2, sort_keys=True) + "\n")


def build_pair(link, output, key, driver, arguments, transform):
    archive = Path(key).name
    output = output.resolve()
    raw = link.read_bytes()
    if output.exists():
        raise FileExistsError(output)
    with TemporaryDirectory(dir=output.parent) as tmp:
        stage = Path(tmp)
        (stage / "release.json").write_bytes(raw)
        result = stage / "result"
        result.mkdir()
        subprocess.run(["docker", "run", "--rm", "--network", "none", "--platform", "linux/amd64",
                        "-v", f"{ROOT}:/work:ro", "-v", f"{stage}:/trial", "rustbox-e2fsprogs:2026-11-24",
                        "python3", "-B", str(Path("/work/scripts") / driver), *arguments], check=True)
        row = direct_receipt(link, key, transform)
        row["candidate_sha256"] = digest(result / archive)
        if raw != link.read_bytes() or row != json.loads((result / "pilot.json").read_bytes()):
            raise ValueError("direct archive or independent source replay differs")
        publish(result, output, archive)
