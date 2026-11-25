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

from check_cargo_private_inlines import IPROUTE2_CARGO_ENGINES, LINK_REPORT, ROOT, digest, layout, rust_inputs
from check_e2fsprogs_dirhash_arrays import source_list_digest
from stage_iproute2_address_protocols import MODULE, compiler_inputs, replace_table


def compile_mounted(archive, route_names=False):
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
    transform = replace_table
    if route_names:
        from iproute2_route_names import replace_route_names
        transform = replace_route_names
    candidate, changes = transform((crate / MODULE).read_bytes())
    subprocess.run(["cargo", "clean", "-p", package, "--release"], cwd=crate, env=env, check=True)
    if built.exists():
        raise ValueError("package clean retained the control archive")
    (crate / MODULE).write_bytes(candidate)
    parent_sources_sha256 = source_list_digest(sources)
    sources[str(MODULE)] = changes["candidate_module_sha256"]
    sha = build(sources)
    if sha == record["control_sha256"]:
        raise ValueError("the live conversion did not change the engine archive")
    record.update(changes, candidate_sha256=sha, compiler_selected_sources=len(sources),
                  parent_sources_sha256=parent_sources_sha256, candidate_sources_sha256=source_list_digest(sources))
    (target / "pilot.json").write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")


def build_pilot(output, link=None, engine="ip", *, route_names=False):
    if output.exists():
        raise ValueError("expected a new pilot output directory")
    raw = LINK_REPORT.read_bytes() if link is None else None
    if raw is not None:
        from iproute2_address_protocol_archive import build_control_view
        link = json.loads(raw) if route_names else build_control_view(json.loads(raw))
    if engine not in IPROUTE2_CARGO_ENGINES:
        raise ValueError(f"unknown IPRoute2 Cargo engine: {engine}")
    if route_names:
        from iproute2_address_protocol_archive import candidate_path, control_view, selected_records
        parents = selected_records(link)
        build_link = control_view(link)
    else:
        build_link = link
    key, = (n for n in build_link["source_library_sha256"] if n.endswith(f"/lib{engine}_audit.a") and "/iproute2-" in n)
    archive = Path(key)
    source, base = layout(archive)
    with tempfile.TemporaryDirectory(dir=ROOT / "work/analysis") as scratch:
        crate, target = Path(scratch) / "source", Path(scratch) / "target"
        shutil.copytree(ROOT / source, crate, ignore=shutil.ignore_patterns("target"))
        target.mkdir()
        module, sources = compiler_inputs(build_link, key, crate)
        selected = archive
        if route_names:
            parent = parents[key]
            module, changes = replace_table(module)
            if changes["candidate_module_sha256"] != parent["candidate_module_sha256"]:
                raise ValueError("route-name pilot requires the verified address-protocol parent")
            (crate / MODULE).write_bytes(module)
            sources[MODULE] = changes["candidate_module_sha256"]
            selected = candidate_path(parent)
        sha = link["source_library_sha256"][str(selected)]
        if digest(ROOT / selected) != sha:
            raise ValueError("pilot parent archive differs from link report")
        (crate / ".rustbox-addrprot-pilot").write_text(sha)
        record = {"archive": key, "control_sha256": sha, "control_binary_sha256": link["binary"]["sha256"],
                  "sources": {str(k): v for k, v in sources.items()}}
        (target / "control.json").write_text(json.dumps(record))
        subprocess.run(["docker", "run", "--rm", "--network", "none", "--platform", "linux/amd64",
                        "-v", f"{ROOT}:/work:ro", "--tmpfs", "/work/.git:ro",
                        "-v", "rustbox-pointer-cargo-registry:/root/.cargo/registry:ro",
                        "-v", f"{crate}:/work/{source}", "-v", f"{target}:/work/{base}",
                        "rustbox-e2fsprogs:2026-11-24", "python3", "-B",
                        "/work/scripts/build_iproute2_address_protocol_pilot.py", "--mounted", key,
                        *(["--route-names"] if route_names else [])], check=True)
        receipt = json.loads((target / "pilot.json").read_bytes())
        candidate = target / "release" / archive.name
        if digest(candidate) != receipt["candidate_sha256"] or (raw is not None and LINK_REPORT.read_bytes() != raw):
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
    group.add_argument("--prepare-copies", action="store_true", help="prepare all 17 pinned production archives")
    group.add_argument("--prepare", action="store_true", help="prepare the pinned production archive")
    group.add_argument("--mounted", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--route-names", action="store_true", help="apply the scope/realm substitution to the current linked parent")
    args = parser.parse_args()
    if args.route_names and not (args.output or args.mounted):
        parser.error("--route-names requires --output")
    if args.mounted:
        compile_mounted(args.mounted, args.route_names)
    elif args.prepare or args.prepare_copies:
        from iproute2_address_protocol_archive import prepare
        prepare(include_copies=args.prepare_copies)
    else:
        build_pilot(args.output.resolve(), route_names=args.route_names)
