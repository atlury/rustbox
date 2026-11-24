#!/usr/bin/env python3
"""Remove compiler-selected private inlines only when the release archive stays byte-identical."""
# SPDX-License-Identifier: 0BSD
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile

TOOL = Path(__file__).resolve().parents[1] / "work/analysis/private-inlines-linux/release/rustbox-inline-audit"
POINTER = re.compile(rb"\*(?:const|mut)\b")


def replay(engine, plan):
    removed = 0
    for name, ranges in plan.items():
        path = Path(name)
        if path.is_absolute() or ".." in path.parts or path.suffix != ".rs":
            raise ValueError(f"invalid pruning path: {name}")
        file = engine / path
        before = file.read_bytes()
        pieces = []
        position = 0
        for start, end in ranges:
            if not position <= start < end <= len(before):
                raise ValueError(f"invalid pruning span in {name}")
            pieces.append(before[position:start])
            body = before[start:end]
            pieces.append(b"\n" * body.count(b"\n"))
            removed += len(POINTER.findall(body))
            position = end
        pieces.append(before[position:])
        file.write_bytes(b"".join(pieces))
    return removed


def prune_identical(engine, rustc_args, archive, depfile):
    if not TOOL.is_file():
        raise FileNotFoundError("missing Linux syntax tool: run scripts/build_private_inline_tool.sh")
    original_sha = hashlib.sha256(archive.read_bytes()).digest()
    with tempfile.TemporaryDirectory() as scratch:
        tmp = Path(scratch)
        diagnostics = tmp / "dead.jsonl"
        # --force-warn overrides both crate-level allow and command-line cap-lints.
        with diagnostics.open("wb") as output:
            subprocess.run([*rustc_args, "--emit=metadata", "-A", "warnings",
                            "--force-warn", "dead_code", "--error-format=json",
                            "lib.rs", "-o", tmp / "crate.rmeta"], cwd=engine, stderr=output, check=True)
        overlay = tmp / "overlay"
        subprocess.run([TOOL, engine, diagnostics, overlay], check=True)
        plan = json.loads((overlay / "ranges.json").read_text())
        if not plan:
            raise ValueError("compiler selected no private inline functions")
        removed = replay(engine, plan)
        for name in plan:
            if (engine / name).read_bytes() != (overlay / name).read_bytes():
                raise ValueError(f"source replay differs from the syntax tool in {name}")
        subprocess.run([*rustc_args, f"--emit=link,dep-info={depfile}", "lib.rs", "-o", archive],
                       cwd=engine, check=True)
        if hashlib.sha256(archive.read_bytes()).digest() != original_sha:
            raise ValueError(f"private-inline cleanup changed release archive bytes: {archive.name}")
        print(f"Verified byte-identical {archive.name} after removing {removed} raw-pointer type occurrences",
              flush=True)
        return plan


def prepare_archive(archive):
    """Publish source provenance only after recompiling the trimmed archive at its original hash."""
    import shlex
    import shutil
    import tomllib
    from build_e2fsprogs_checksums import stage

    name = archive.parent.name
    translations = archive.parents[2]
    manifest = json.loads(archive.with_suffix(".sources.json").read_text())
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    if manifest["archive_sha256"] != digest:
        raise ValueError(f"stale release archive {archive}")
    key = hashlib.sha256((manifest["build_key"] + digest).encode() + TOOL.read_bytes()
                         + Path(__file__).read_bytes()).hexdigest()
    proof = archive.with_suffix(f".inlines-{key}.json")
    if proof.exists():
        record = json.loads(proof.read_text())
        if record["key"] != key or record["archive_sha256"] != digest:
            raise ValueError(f"stale private-inline evidence {proof}")
        return proof

    deps = translations / "cargo-target" / name / "release/deps"
    with tempfile.TemporaryDirectory() as scratch, tempfile.TemporaryDirectory(dir=archive.parent) as out:
        engine = Path(scratch) / name
        shutil.copytree(translations / name / f"{name}-final", engine,
                        ignore=shutil.ignore_patterns("target"))
        stage(engine)
        for relative, expected in manifest["sources"].items():
            if hashlib.sha256((engine / relative).read_bytes()).hexdigest() != expected:
                raise ValueError(f"baseline source changed: {relative}")
        config = tomllib.loads((engine / "Cargo.toml").read_text())
        args = ["rustc", "+nightly-2023-04-15", "--edition=2021", "--crate-type=staticlib", "--crate-name",
                config["lib"]["name"], "-C", "opt-level=3", "--cap-lints=allow",
                "--remap-path-prefix", f"{scratch}=/rustbox-e2fsprogs", "-L", f"dependency={deps}"]
        for dep in config["dependencies"]:
            rust_name = dep.replace("-", "_")
            lib, = deps.glob(f"lib{rust_name}-*.rlib")
            args.extend(["--extern", f"{rust_name}={lib}"])
        staged = Path(out) / archive.name
        shutil.copyfile(archive, staged)
        depfile = Path(out) / "compiler.d"
        plan = prune_identical(engine, args, staged, depfile)
        rule = depfile.read_text().splitlines()[0].split(": ", 1)[1]
        inputs = {p for p in shlex.split(rule) if p.endswith(".rs")}
        if inputs != set(manifest["sources"]) or not set(plan) <= inputs:
            raise ValueError("compiler source list changed during private-inline cleanup")
        record = {"key": key, "archive_sha256": digest, "ranges": plan,
                  "sources": {n: hashlib.sha256((engine / n).read_bytes()).hexdigest() for n in plan}}
        pending = Path(out) / proof.name
        pending.write_text(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
        # The two archives have the same SHA. Publish the candidate from the trimmed sources.
        staged.replace(archive)
        pending.replace(proof)
    return proof


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archives", type=Path, nargs="+")
    args = parser.parse_args()
    for archive in args.archives:
        print(prepare_archive(archive.resolve()), flush=True)
