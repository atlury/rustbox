#!/usr/bin/env python3
"""Compile a private-inline cleanup against its unchanged E2fsprogs archive."""
# SPDX-License-Identifier: 0BSD

import argparse
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import tomllib

ROOT = Path(__file__).resolve().parents[1]
TRANSLATIONS = ROOT / "work/analysis/e2fsprogs-1.47.4/program-translations"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compiler(engine, deps, scratch):
    config = tomllib.loads((engine / "Cargo.toml").read_text())
    args = ["rustc", "+nightly-2023-04-15", "--edition=2021", "--crate-name", config["lib"]["name"],
            "-C", "opt-level=3", "--remap-path-prefix", f"{scratch}=/rustbox-{config['lib']['name'].removesuffix('_audit')}",
            "-L", f"dependency={deps}"]
    for dep in config["dependencies"]:
        name = dep.replace("-", "_")
        library, = deps.glob(f"lib{name}-*.rlib")
        args.extend(["--extern", f"{name}={library}"])
    return args


def apply_overlay(engine, overlay):
    count = re.compile(rb"\*(?:const|mut)\b")
    removed = 0
    for updated in sorted(overlay.rglob("*.rs")):
        original = engine / updated.relative_to(overlay)
        before = original.read_bytes()
        after = updated.read_bytes()
        if before.count(b"\n") != after.count(b"\n"):
            raise ValueError(f"source coordinates changed in {original}")
        removed += len(count.findall(before)) - len(count.findall(after))
        original.write_bytes(after)
    return removed


def verify_badblocks(tmp):
    image = tmp / "disk.img"
    image.write_bytes(bytes(range(256)) * 4096)
    listed = tmp / "already-bad"
    listed.write_text("7\n13\n")
    original = digest(image)
    oracle = "/rustbox-e2fsprogs/stage-gcc/sbin/badblocks"
    for cli in ([], ["-h"], ["-b", "1024", "-c", "8", str(image), "95", "5"],
                ["-i", str(listed), str(image), "127", "0"]):
        results = []
        for program in (oracle, tmp / "original", tmp / "trimmed"):
            run = subprocess.run(["badblocks", *cli], executable=program,
                                 env=dict(os.environ, LC_ALL="C", TZ="UTC"), capture_output=True)
            results.append((run.returncode, run.stdout, run.stderr))
            if digest(image) != original:
                raise RuntimeError("read-only command modified the input image")
        if len(set(results)) != 1:
            raise RuntimeError(f"badblocks differs from canonical for {cli}")
    print("All four canonical badblocks comparisons passed.", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["lint", "verify"])
    parser.add_argument("name")
    parser.add_argument("scratch", type=Path)
    args = parser.parse_args()
    if not re.fullmatch(r"[a-z0-9_]+", args.name):
        parser.error("expected an engine name")
    source = TRANSLATIONS / args.name / f"{args.name}-final"
    deps = TRANSLATIONS / "cargo-target" / args.name / "release/deps"
    with tempfile.TemporaryDirectory() as scratch:
        tmp = Path(scratch)
        if args.action == "lint":
            with (args.scratch / "rustc.jsonl").open("w") as output:
                subprocess.run([*compiler(source, deps, tmp), "--crate-type=rlib", "--emit=metadata",
                                "-A", "warnings", "--force-warn", "dead_code", "--error-format=json",
                                "lib.rs", "-o", tmp / "engine.rmeta"], cwd=source, stderr=output, check=True)
            return
        engine = tmp / "engine"
        shutil.copytree(source, engine, ignore=shutil.ignore_patterns("target"))
        rustc = compiler(engine, deps, tmp)
        stamps = []
        for variant in ("original", "trimmed"):
            if variant == "trimmed":
                removed = apply_overlay(engine, args.scratch / "overlay")
                print(f"Removed {removed} raw-pointer type occurrences.", flush=True)
            archive = tmp / "engine.a"
            subprocess.run([*rustc, "--crate-type=staticlib", "--cap-lints=allow", "lib.rs",
                            "-o", archive], cwd=engine, check=True)
            binary = tmp / variant
            subprocess.run(["clang-18", "-O2", "-Wl,--gc-sections",
                            f"-DRUSTBOX_E2FSPROGS_ENTRY=rustbox_e2fsprogs_{args.name}_main",
                            ROOT / "bridges/e2fsprogs_program_main.c", archive, "-lblkid", "-luuid",
                            "-lfuse3", "-ldl", "-lpthread", "-lm", "-o", binary], check=True)
            stripped = tmp / (variant + ".stripped")
            subprocess.run(["strip", "-o", stripped, binary], check=True)
            stamps.append(tuple(map(digest, (archive, binary, stripped))))
        if stamps[0] != stamps[1]:
            raise RuntimeError(f"archive or executable SHA-256 differs: {stamps}")
        print("Identical archive, executable and stripped executable SHA-256:", *stamps[0], flush=True)
        if args.name == "badblocks":
            verify_badblocks(tmp)


if __name__ == "__main__":
    main()
