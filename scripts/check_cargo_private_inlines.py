#!/usr/bin/env python3
"""Check private inline cleanup against the Cargo archive selected by the Linux release."""
# SPDX-License-Identifier: 0BSD

import argparse
import hashlib
import json
import concurrent.futures
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
LINK_REPORT = ROOT / "work/analysis/rustbox-multicall-link.json"
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
    if target.name == "target":
        return target.parent, target
    if target.parent.name == "cargo-target":
        crate = target.parent.parent / target.name / f"{target.name}-final"
        return crate, target
    raise ValueError(f"unknown Cargo build layout: {archive}")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
    with tempfile.TemporaryDirectory() as scratch:
        tmp = Path(scratch)
        diagnostics = tmp / "dead.jsonl"
        with diagnostics.open("w") as output:
            with subprocess.Popen(["cargo", "check", "--message-format=json", *flags],
                                  env=dict(env, RUSTFLAGS="-A warnings --force-warn dead_code"),
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
        removed = replay(crate, plan)
        subprocess.run(["cargo", "clean", "--release", "--manifest-path", crate / "Cargo.toml"],
                       env=env, check=True)
        subprocess.run(["cargo", "build", *flags], cwd=crate, env=env, check=True)
        if digest(archive) != selected_sha:
            raise RuntimeError(f"private-inline cleanup changed the selected {name} release archive")
        proof = {"archive_sha256": selected_sha, "ranges": plan,
                 "sources": {p: digest(crate / p) for p in plan}}
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
        key_hash = hashlib.sha256()
        for path in (Path(__file__), ROOT / "scripts/prune_private_inlines.py", TOOL):
            key_hash.update(bytes.fromhex(digest(path)))
        key_hash.update(bytes.fromhex(expected))
        # A compiler-selected file or a change in crate configuration invalidates the proof.
        import shlex
        rule = (ROOT / archive).with_suffix(".d").read_text().splitlines()[0].split(": ", 1)[1]
        selected = {Path(n).relative_to("/work") for n in shlex.split(rule) if n.endswith(".rs")}
        for path in sorted(selected | {source / f for f in ("Cargo.toml", "Cargo.lock", "rust-toolchain.toml")}):
            key_hash.update(str(path).encode() + b"\0" + bytes.fromhex(digest(ROOT / path)))
        key = key_hash.hexdigest()
        saved = (ROOT / archive).with_suffix(f".inlines-{key}.json")
        if saved.is_file():
            old = json.loads(saved.read_text())
            if old["key"] != key or old["archive_sha256"] != expected:
                raise ValueError(f"stale Cargo private-inline proof: {saved}")
            return {"file": saved.name, "sha256": digest(saved)}
    registry = (["-v", "rustbox-pointer-cargo-registry:/root/.cargo/registry:ro"]
                if archive.parts[2] == "iproute2-7.3.0" else [])
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
            if not record["ranges"] or not {source / p for p in record["ranges"]} <= selected:
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
    else:
        release, engines = "7.3.0", IPROUTE2_CARGO_ENGINES
    target = Path(f"work/analysis/{package}-{release}/program-translations/cargo-target")
    index_file = ROOT / f"work/analysis/{package}-cargo-inline-proofs.json"
    paths = [target / name / "release" / f"lib{name}_audit.a" for name in engines]
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
