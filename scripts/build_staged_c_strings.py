#!/usr/bin/env python3
"""Cold-build native strings in the directly compiled E2fsprogs engines and IPRoute2 bridge."""
# SPDX-License-Identifier: GPL-3.0-or-later
from hashlib import sha256
import json
import shutil
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

from cargo_source_parent import cargo_origin
from check_cargo_private_inlines import ROOT, digest
from check_e2fsprogs_dirhash_arrays import compile_staged, source_list_digest


def compile_archive(snapshot, output, key):
    from audit_linked_pointers import measure
    from build_c_string_literal_pilot import substitute
    from e2fsprogs_foreign_declarations import staged_compiler_inputs
    from e2fsprogs_dirhash_archives import control_view
    import curl_manual_archive
    import iproute2_address_protocol_archive as address

    if not output.is_dir() or any(output.iterdir()):
        raise ValueError("direct compilation requires an empty output directory")
    link = json.loads(snapshot.read_bytes())
    if key in link.get("native_c_strings", {}):
        link["native_c_strings"] = {k: v for k, v in link["native_c_strings"].items() if k != key}
    selected = Path(key)
    original = cargo_origin(link, key)
    parent = address.control_view(control_view(curl_manual_archive.parent_view(link)))
    expected = link["source_library_sha256"][key]
    if digest(ROOT / selected) != expected:
        raise ValueError("the staged engine differs from the link")
    with TemporaryDirectory() as directory:
        scratch = Path(directory)
        crate, inputs, rustc = staged_compiler_inputs(parent, original, scratch)
        sources = {}

        def capture(archive, module, checksum, data):
            name = str(module)
            if archive != selected or name in sources or name not in inputs:
                raise ValueError("unexpected directly compiled source")
            (crate / module).write_bytes(data)
            sources[name] = checksum.hex()

        measure(link, inspect_module=capture, archive_pair=(original, selected))
        built = scratch / selected.name
        if sources.keys() != inputs or compile_staged(crate, inputs, rustc, built) != expected:
            raise ValueError("direct compiler recipe failed to reproduce the selected archive")
        replacements, changes = substitute(crate, sources)
        if not replacements or not replacements.keys() <= inputs:
            raise ValueError("expected checked C strings in compiler-selected modules")
        for module, new in replacements.items():
            if digest(crate / module) != sources[module]:
                raise ValueError("parent source changed during compilation")
            (crate / module).write_bytes(new)
        candidate = compile_staged(crate, inputs, rustc, built)
        after = {name: digest(crate / name) for name in inputs}
        predicted = {**sources, **{name: sha256(new).hexdigest() for name, new in replacements.items()}}
        if after != predicted:
            raise ValueError("compiler source set or bytes changed after substitution")
        row = dict(archive=key, rustc_archive=str(original), control_binary_sha256=link["binary"]["sha256"],
                   control_sha256=expected, candidate_sha256=candidate, compiler_selected_sources=len(inputs),
                   parent_sources_sha256=source_list_digest(sources), candidate_sources_sha256=source_list_digest(after), **changes)
        shutil.copyfile(built, output / selected.name)
        if digest(output / selected.name) != candidate:
            raise ValueError("candidate archive copy differed")
        (output / "pilot.json").write_text(json.dumps(row, indent=2, sort_keys=True) + "\n")


def build(link, output, key):
    output = output.resolve()
    raw = link.read_bytes()
    if output.exists():
        raise ValueError("direct compiler comparison needs a new directory")
    with TemporaryDirectory(dir=output.parent) as temp:
        stage = Path(temp)
        (stage / "snapshot.json").write_bytes(raw)
        result = stage / "result"
        result.mkdir()
        subprocess.run(["docker", "run", "--rm", "--network", "none", "--platform", "linux/amd64",
                        "-v", f"{ROOT}:/work:ro", "-v", f"{stage}:/trial", "rustbox-e2fsprogs:2026-11-24",
                        "python3", "-B", "/work/scripts/build_staged_c_strings.py",
                        "/trial/snapshot.json", "/trial/result", key], check=True)
        if link.read_bytes() != raw:
            raise ValueError("selected release changed during direct compilation")
        result.rename(output)


if __name__ == "__main__":
    compile_archive(Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3])
