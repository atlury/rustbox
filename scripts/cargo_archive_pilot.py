"""Reproduce a complete Cargo archive, change one verified module, and record the compiler inputs."""
# SPDX-License-Identifier: GPL-2.0-or-later
import json
import os
import subprocess

from check_cargo_private_inlines import ROOT, digest, layout, rust_inputs
from check_e2fsprogs_dirhash_arrays import source_list_digest


def compile_mounted_archive(archive, module, transform, marker):
    import tomllib

    source, base = layout(archive)
    crate, target = ROOT / source, ROOT / base
    record = json.loads((target / "control.json").read_bytes())
    if record["archive"] != str(archive) or (crate / marker).read_text() != record["control_sha256"]:
        raise ValueError("expected this archive's disposable pilot directories")
    built = ROOT / archive
    if built.exists():
        raise ValueError("the isolated control must build from an empty target")
    channel = tomllib.loads((crate / "rust-toolchain.toml").read_text())["toolchain"]["channel"]
    package = tomllib.loads((crate / "Cargo.toml").read_text())["package"]["name"]
    env = dict(os.environ, CARGO_TARGET_DIR=str(target), RUSTUP_TOOLCHAIN=channel)

    def build(sources):
        subprocess.run(["cargo", "build", "--locked", "--offline", "--release"], cwd=crate, env=env, check=True)
        compiled = {str(p.relative_to(source)): digest(ROOT / p) for p in rust_inputs(built)}
        if compiled != sources:
            raise ValueError("archive compiler input set or source bytes differ")
        return digest(built)

    sources = record.pop("sources")
    if build(sources) != record["control_sha256"]:
        raise ValueError("cold Cargo build failed to reproduce the linked control archive")
    candidate, changes = transform((crate / module).read_bytes())
    subprocess.run(["cargo", "clean", "-p", package, "--release"], cwd=crate, env=env, check=True)
    if built.exists():
        raise ValueError("package clean retained the control archive")
    (crate / module).write_bytes(candidate)
    parent_sources_sha256 = source_list_digest(sources)
    sources[str(module)] = changes["candidate_module_sha256"]
    sha = build(sources)
    if sha == record["control_sha256"]:
        raise ValueError("the live conversion did not change the engine archive")
    record.update(changes, candidate_sha256=sha, compiler_selected_sources=len(sources),
                  parent_sources_sha256=parent_sources_sha256, candidate_sources_sha256=source_list_digest(sources))
    (target / "pilot.json").write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")


def verify_source_substitution(record, sources, changes, module):
    if (len(sources) != record["compiler_selected_sources"] or any(record[k] != v for k, v in changes.items())
            or sources[str(module)] != record["control_module_sha256"]
            or source_list_digest(sources) != record["parent_sources_sha256"]
            or source_list_digest({**sources, str(module): changes["candidate_module_sha256"]}) != record["candidate_sources_sha256"]):
        raise ValueError("compiler inputs differ from the pinned archive substitution")
