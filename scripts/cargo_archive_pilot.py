"""Reproduce a complete Cargo archive, change verified modules, and record the compiler inputs."""
# SPDX-License-Identifier: GPL-2.0-or-later
import hashlib
import json
import os
from pathlib import Path
import subprocess
import shutil
from tempfile import TemporaryDirectory

from check_cargo_private_inlines import ROOT, digest, layout, rust_inputs
from check_e2fsprogs_dirhash_arrays import source_list_digest


def compile_mounted_archive(archive, module, transform, marker):
    def substitute(crate, sources):
        candidate, changes = transform((crate / module).read_bytes())
        if (sources[str(module)] != changes["control_module_sha256"]
                or hashlib.sha256(candidate).hexdigest() != changes["candidate_module_sha256"]):
            raise ValueError("source substitution differs from the module receipt")
        return {str(module): candidate}, changes

    compile_mounted_sources(archive, substitute, marker, allow_identical=False)


def compile_mounted_sources(archive, substitute, marker, *, allow_identical):
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
    replacements, changes = substitute(crate, sources.copy())
    if not replacements or not replacements.keys() <= sources.keys():
        raise ValueError("substitution must change compiler-selected sources")
    subprocess.run(["cargo", "clean", "-p", package, "--release"], cwd=crate, env=env, check=True)
    if built.exists():
        raise ValueError("package clean retained the control archive")
    parent_sources_sha256 = source_list_digest(sources)
    for name, data in replacements.items():
        path = crate / name
        if Path(name).is_absolute() or ".." in Path(name).parts or digest(path) != sources[name]:
            raise ValueError(f"unexpected source before substitution: {name}")
        path.write_bytes(data)
        sources[name] = digest(path)
    sha = build(sources)
    if not allow_identical and sha == record["control_sha256"]:
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


def stage_selected_archive(link_file, out, key, marker, script, prepare_crate=None, omit_layer=None):
    from audit_linked_pointers import measure
    raw = link_file.read_bytes()
    link = json.loads(raw)
    sha = link["source_library_sha256"][key]
    archive = Path(key)
    src, base = layout(archive)
    if out.exists() or digest(ROOT / archive) != sha:
        raise ValueError("expected an empty destination and the linked archive")
    layers = ("source_library_sha256", "linked_private_inline_proofs", "linked_second_inline_proofs",
              "linked_foreign_declaration_proofs", "shared_stdio_layouts")
    receipts = {k: {key: link[k][key]} for k in layers if k != omit_layer and key in link.get(k, {})}
    with TemporaryDirectory(dir=out.parent) as tmp:
        crate, target, result = (Path(tmp) / n for n in ("crate", "target", "result"))
        shutil.copytree(ROOT / src, crate, ignore=shutil.ignore_patterns("target"))
        target.mkdir()
        if prepare_crate is not None:
            prepare_crate(crate)
        sources = {}

        def capture(selected, module, checksum, data):
            if selected != archive or str(module) in sources:
                raise ValueError("unexpected archive compiler input")
            (crate / module).write_bytes(data)
            sources[str(module)] = checksum.hex()

        measure(dict(receipts, binary=link["binary"]), inspect_module=capture)
        (crate / marker).write_text(sha)
        (target / "control.json").write_text(json.dumps(dict(archive=key, control_sha256=sha,
            control_binary_sha256=link["binary"]["sha256"], sources=sources)))
        subprocess.run(["docker", "run", "--rm", "--network", "none", "--platform", "linux/amd64",
                        "-v", f"{ROOT}:/work:ro", "--tmpfs", "/work/.git:ro",
                        "-v", f"{crate}:/work/{src}", "-v", f"{target}:/work/{base}",
                        "-v", "rustbox-pointer-cargo-registry:/root/.cargo/registry:ro",
                        "rustbox-e2fsprogs:2026-11-24", "python3", "-B",
                        str(Path("/work/scripts") / script), "--mounted", key], check=True)
        row = json.loads((target / "pilot.json").read_bytes())
        candidate = target / "release" / archive.name
        if digest(candidate) != row["candidate_sha256"] or row["control_sha256"] != sha or link_file.read_bytes() != raw:
            raise ValueError("archive or selected release changed during the experiment")
        result.mkdir()
        candidate.replace(result / archive.name)
        (target / "pilot.json").replace(result / "pilot.json")
        result.rename(out)
        print(json.dumps(row, sort_keys=True))
