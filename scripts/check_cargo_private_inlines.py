#!/usr/bin/env python3
"""Check private inline cleanup against the Cargo archive selected by the Linux release."""
# SPDX-License-Identifier: 0BSD

import argparse
import hashlib
import json
import concurrent.futures
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
LINK_REPORT = ROOT / "work/analysis/rustbox-multicall-link.json"
# Both released verifiers accept only a strict, byte-identical whole-archive rebuild.
STRICT_VERIFIERS = (
    "28bd1667cb695e690698dc5ccc124321045417e971b9e5739d09a0abb44f11cc",  # e881b0d, crate clean
    "fbaf8906696946d8ae9984570628898f7bef46795995601af852df0bc6e8e89e",  # 67c7ae2, full target clean
)
# This producer supports both verified layouts and binds the padding implementation.
OFFSET_VERIFIER = "86c7a52bb69f8f4e27b85bbc14f9c3ffbe9cffbd6b697981b463baaf5dfcea58"
CARGO_ENGINES = ("chattr", "e4crypt", "filefrag", "fsck", "logsave", "lsattr", "mklost_found")
IPROUTE2_CARGO_ENGINES = ("arpd", "dcb", "devlink", "dpll", "genl", "ifstat", "ip", "lnstat", "netshaper",
                         "nstat", "rdma", "rtacct", "rtmon", "ss", "tc", "tipc", "vdpa")


def layout(archive):
    """Map an original Cargo-built release archive to its crate and target directories."""
    if archive.is_absolute() or ".." in archive.parts or archive.parts[:2] != ("work", "analysis"):
        raise ValueError("expected a repository-relative archive from the Linux link report")
    if archive.suffix != ".a" or archive.parent.name != "release":
        raise ValueError("expected an original Cargo release archive")
    target = archive.parents[1]
    if target.name == "cargo-target" and archive.name.endswith("_audit.a"):
        name = archive.name.removeprefix("lib").removesuffix("_audit.a")
        return target.parent / name / f"{name}-stable", target
    if target.name == "target":
        return target.parent, target
    if target.parent.name == "cargo-target":
        crate = target.parent.parent / target.name / f"{target.name}-final"
        return crate, target
    raise ValueError(f"unknown Cargo build layout: {archive}")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rust_inputs(archive):
    rule = archive.with_suffix(".d").read_text().splitlines()[0].split(": ", 1)[1]
    return {Path(name).relative_to("/work") for name in shlex.split(rule) if name.endswith(".rs")}


def verify_in_container(relative_archive, selected_sha):
    import tomllib
    from prune_private_inlines import TOOL, replay

    source, target_dir = layout(relative_archive)
    crate, target = ROOT / source, ROOT / target_dir
    archive = ROOT / relative_archive
    if any((directory / ".rustbox-inline-scratch").read_text() != selected_sha
           for directory in (crate, target)):
        raise ValueError("expected a disposable source and Cargo target")
    config = tomllib.loads((crate / "rust-toolchain.toml").read_text())
    env = dict(os.environ, CARGO_TARGET_DIR=str(target), RUSTUP_TOOLCHAIN=config["toolchain"]["channel"])
    name = crate.name
    flags = ["--locked", "--offline", "--release", "--manifest-path", str(crate / "Cargo.toml")]
    subprocess.run(["cargo", "build", *flags], cwd=crate, env=env, check=True)
    if digest(archive) != selected_sha:
        raise RuntimeError(f"{name} clean Cargo build differs from its selected archive")
    original_inputs = rust_inputs(archive)
    with tempfile.TemporaryDirectory() as scratch:
        tmp = Path(scratch)
        diagnostics = tmp / "dead.jsonl"
        with diagnostics.open("w") as output:
            with subprocess.Popen(["cargo", "rustc", "--message-format=json", "--lib", *flags,
                                   "--", "-A", "warnings", "--force-warn", "dead_code"],
                                  env=env,
                                  stdout=subprocess.PIPE, text=True, cwd=crate) as child:
                for line in child.stdout:
                    record = json.loads(line)
                    if record.get("reason") == "compiler-message" and record.get("target", {}).get("src_path") == str(crate / "lib.rs"):
                        print(json.dumps(record["message"]), file=output)
                if child.wait():
                    raise RuntimeError("Cargo could not produce the private-function diagnostics")
        overlay = tmp / "overlay"
        subprocess.run([TOOL, crate, diagnostics, overlay], check=True)
        plan = json.loads((overlay / "ranges.json").read_text())
        if not {source / n for n in plan} <= original_inputs:
            raise ValueError("private-inline ranges must belong to compiler-selected sources")
        originals = {n: (crate / n).read_bytes() for n in plan}
        removed = replay(crate, plan)
        package = tomllib.loads((crate / "Cargo.toml").read_text())["package"]["name"]

        def rebuild_matches():
            subprocess.run(["cargo", "clean", "--release", "-p", package, "--manifest-path", crate / "Cargo.toml"],
                           env=env, check=True)
            if archive.exists():
                raise RuntimeError("package clean retained the candidate archive")
            subprocess.run(["cargo", "build", *flags], cwd=crate, env=env, check=True)
            if rust_inputs(archive) != original_inputs:
                raise RuntimeError(f"compiler-selected source files changed after cleaning {name}")
            return digest(archive) == selected_sha

        proof = {"archive_sha256": selected_sha, "ranges": plan}
        if not rebuild_matches():
            from inline_source_layout import pad_removed_items
            pad_removed_items(crate, plan, originals)
            if not rebuild_matches():
                raise RuntimeError(f"private-inline cleanup changed the selected {name} release archive")
            proof["source_layout"] = "byte_offsets"
        proof["sources"] = {p: digest(crate / p) for p in plan}
        (target / ".rustbox-private-inlines.json").write_text(json.dumps(proof, sort_keys=True))
        print(json.dumps({"engine": name, "archive_sha256": selected_sha,
                          "changed_files": len(plan), "private_functions_removed": sum(map(len, plan.values())),
                          "raw_pointer_type_tokens_removed": removed}), flush=True)


def check_linux_cargo(archive, publish=False):
    source, base = layout(archive)
    expected = digest(ROOT / archive)
    if not publish:
        hashes = json.loads(LINK_REPORT.read_text())["source_library_sha256"]
        if expected != hashes[str(archive)]:
            raise ValueError(f"source archive differs from selected Linux link: {archive}")
    if publish:
        from prune_private_inlines import TOOL
        inputs = bytearray()
        for path in (ROOT / "scripts/prune_private_inlines.py", TOOL):
            inputs.extend(bytes.fromhex(digest(path)))
        inputs.extend(bytes.fromhex(expected))
        selected = rust_inputs(ROOT / archive)
        for path in sorted(selected | {source / f for f in ("Cargo.toml", "Cargo.lock", "rust-toolchain.toml")}):
            inputs.extend(str(path).encode() + b"\0" + bytes.fromhex(digest(ROOT / path)))
        layout_digest = bytes.fromhex(digest(ROOT / "scripts/inline_source_layout.py"))
        verifier = bytes.fromhex(digest(Path(__file__))) + layout_digest
        key = hashlib.sha256(verifier + inputs).hexdigest()
        saved = (ROOT / archive).with_suffix(f".inlines-{key}.json")
        # Reuse strict receipts under their actual producer and complete input digest.
        # That producer accepted only archives that matched after the first rebuild.
        strict_keys = [hashlib.sha256(bytes.fromhex(producer) + inputs).hexdigest()
                       for producer in STRICT_VERIFIERS]
        offset_key = hashlib.sha256(bytes.fromhex(OFFSET_VERIFIER) + layout_digest + inputs).hexdigest()
        for candidate_key in (key, offset_key, *strict_keys):
            candidate = (ROOT / archive).with_suffix(f".inlines-{candidate_key}.json")
            if candidate.is_file():
                record = json.loads(candidate.read_text())
                if (record["key"] != candidate_key or record["archive_sha256"] != expected
                        or record.get("source_layout", "lines") not in ("lines", "byte_offsets")
                        or (candidate_key in strict_keys and "source_layout" in record)):
                    raise ValueError(f"stale Cargo private-inline proof: {candidate}")
                return {"file": candidate.name, "sha256": digest(candidate)}
    registry = (["-v", "rustbox-pointer-cargo-registry:/root/.cargo/registry:ro"]
                if archive.parts[2] in ("iproute2-7.3.0", "inetutils-2.8", "curl-8.23.0") else [])
    with tempfile.TemporaryDirectory(dir=ROOT / "work/analysis") as scratch:
        tmp = Path(scratch)
        shutil.copytree(ROOT / source, tmp / "source", ignore=shutil.ignore_patterns("target"))
        (tmp / "output").mkdir()
        for directory in ("source", "output"):
            (tmp / directory / ".rustbox-inline-scratch").write_text(expected)
        # Cargo embeds paths in metadata. Mount disposable inputs at the original
        # paths so the candidate can be compared with the production archive.
        subprocess.run(["docker", "run", "--rm", "--network", "none", "--platform", "linux/amd64",
                        "--workdir", "/work", "-v", f"{ROOT}:/work:ro", *registry,
                        "-v", f"{tmp / 'source'}:/work/{source}",
                        "-v", f"{tmp / 'output'}:/work/{base}", "rustbox-e2fsprogs:2026-11-24",
                        "python3", "-B", "/work/scripts/check_cargo_private_inlines.py",
                        str(archive), "--verify-mounted-copy", expected], check=True)

        if publish:
            record = json.loads((tmp / "output/.rustbox-private-inlines.json").read_text())
            if not {source / p for p in record["ranges"]} <= selected:
                raise RuntimeError("pruning ranges must belong to compiler-selected Cargo inputs")
            compiled = tmp / "output/release" / archive.name
            if digest(compiled) != expected or record["archive_sha256"] != expected:
                raise RuntimeError("rebuilt Cargo archive hash changed during publication")
            record["key"] = key
            proof = tmp / saved.name
            proof.write_text(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
            compiled.replace(ROOT / archive)
            proof.replace(saved)
            return {"file": saved.name, "sha256": digest(saved)}


def prepare_package(package):
    if package == "e2fsprogs":
        release, engines = "1.47.4", CARGO_ENGINES
    elif package == "iproute2":
        release, engines = "7.3.0", IPROUTE2_CARGO_ENGINES
    else:
        from link_rustbox_multicall import INETUTILS_PROGRAMS
        release, engines = "2.8", INETUTILS_PROGRAMS
    target = Path(f"work/analysis/{package}-{release}/program-translations/cargo-target")
    index_file = ROOT / f"work/analysis/{package}-cargo-inline-proofs.json"
    paths = [(target if package == "inetutils" else target / name) / "release" / f"lib{name}_audit.a"
             for name in engines]
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as workers:
        futures = {path: workers.submit(check_linux_cargo, path, True) for path in paths}
        index = {str(path): task.result() for path, task in futures.items()}
    with tempfile.NamedTemporaryFile(mode="w", dir=index_file.parent, delete=False) as file:
        json.dump(index, file, indent=2, sort_keys=True)
        file.write("\n")
    Path(file.name).replace(index_file)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path, nargs="?")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--prepare-e2fsprogs", action="store_const", const="e2fsprogs", dest="package")
    group.add_argument("--prepare-iproute2", action="store_const", const="iproute2", dest="package")
    group.add_argument("--prepare-inetutils", action="store_const", const="inetutils", dest="package")
    parser.add_argument("--verify-mounted-copy", metavar="SHA256")
    args = parser.parse_args()
    if args.package and not args.archive and not args.verify_mounted_copy:
        prepare_package(args.package)
    elif args.archive is None or args.package:
        parser.error("use an archive path or a package preparation option")
    elif args.verify_mounted_copy:
        if ROOT != Path("/work") or not Path("/.dockerenv").exists():
            parser.error("verification requires the isolated Linux checkout")
        verify_in_container(args.archive, args.verify_mounted_copy)
    else:
        check_linux_cargo(args.archive)
