#!/usr/bin/env python3
"""Rebuild the complete IPRoute2 ip control and address-protocol candidate in isolated Cargo directories."""
# SPDX-License-Identifier: GPL-2.0-or-later
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from check_cargo_private_inlines import LINK_REPORT, ROOT, digest, layout, rust_inputs
from stage_iproute2_address_protocols import MODULE, compiler_inputs, replace_table


def compile_mounted(archive):
    import tomllib

    source, base = layout(archive)
    crate, target = ROOT / source, ROOT / base
    record = json.loads((target / "control.json").read_bytes())
    if record["archive"] != str(archive) or (crate / ".rustbox-addrprot-pilot").read_text() != record["control_sha256"]:
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
    candidate, changes = replace_table((crate / MODULE).read_bytes())
    subprocess.run(["cargo", "clean", "-p", package, "--release"], cwd=crate, env=env, check=True)
    if built.exists():
        raise ValueError("package clean retained the control archive")
    (crate / MODULE).write_bytes(candidate)
    sources[str(MODULE)] = changes["candidate_module_sha256"]
    sha = build(sources)
    if sha == record["control_sha256"]:
        raise ValueError("the live conversion did not change the engine archive")
    record.update(changes, candidate_sha256=sha, compiler_selected_sources=len(sources))
    (target / "pilot.json").write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")


def build_pilot(output):
    if output.exists():
        raise ValueError("expected a new pilot output directory")
    raw = LINK_REPORT.read_bytes()
    link = json.loads(raw)
    key, = (n for n in link["source_library_sha256"] if n.endswith("/libip_audit.a"))
    archive = Path(key)
    source, base = layout(archive)
    with tempfile.TemporaryDirectory(dir=ROOT / "work/analysis") as scratch:
        crate, target = Path(scratch) / "source", Path(scratch) / "target"
        shutil.copytree(ROOT / source, crate, ignore=shutil.ignore_patterns("target"))
        target.mkdir()
        _, sources = compiler_inputs(link, key, crate)
        sha = link["source_library_sha256"][key]
        (crate / ".rustbox-addrprot-pilot").write_text(sha)
        record = {"archive": key, "control_sha256": sha, "control_binary_sha256": link["binary"]["sha256"],
                  "sources": {str(k): v for k, v in sources.items()}}
        (target / "control.json").write_text(json.dumps(record))
        subprocess.run(["docker", "run", "--rm", "--network", "none", "--platform", "linux/amd64",
                        "-v", f"{ROOT}:/work:ro", "--tmpfs", "/work/.git:ro",
                        "-v", "rustbox-pointer-cargo-registry:/root/.cargo/registry:ro",
                        "-v", f"{crate}:/work/{source}", "-v", f"{target}:/work/{base}",
                        "rustbox-e2fsprogs:2026-11-24", "python3", "-B",
                        "/work/scripts/build_iproute2_address_protocol_pilot.py", "--mounted", key], check=True)
        receipt = json.loads((target / "pilot.json").read_bytes())
        candidate = target / "release" / archive.name
        if digest(candidate) != receipt["candidate_sha256"] or LINK_REPORT.read_bytes() != raw:
            raise ValueError("pilot archive or release changed after build")
        with tempfile.TemporaryDirectory(dir=output.parent) as staging:
            result = Path(staging) / "result"
            result.mkdir()
            shutil.copy2(candidate, result / archive.name)
            shutil.copy2(target / "pilot.json", result / "pilot.json")
            result.rename(output)
        print(json.dumps(receipt, sort_keys=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--output", type=Path, help="new directory under an existing parent")
    group.add_argument("--mounted", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.mounted:
        compile_mounted(args.mounted)
    else:
        build_pilot(args.output.resolve())
