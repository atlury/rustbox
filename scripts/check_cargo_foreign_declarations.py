#!/usr/bin/env python3
"""Trial private foreign declaration removal in a disposable linked Cargo engine."""
# SPDX-License-Identifier: 0BSD
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from check_cargo_private_inlines import ROOT, digest, layout, rust_inputs
from check_next_inline_layer import apply_receipt, read_second_layer
from e2fsprogs_foreign_declarations import publish_verified, read_proof, selection, staged_archives, validate_proof, verify_declarations

MANIFEST = ROOT / "batches/multicall-cargo-foreign-declarations.json"


def compile_trial(archive, sha):
    import tomllib

    source, base = layout(archive)
    crate, target = ROOT / source, ROOT / base
    if any((directory / ".rustbox-foreign-trial").read_text() != sha for directory in (crate, target)):
        raise ValueError("expected a disposable source and target")
    if (ROOT / archive).exists():
        raise ValueError("control requires an empty target")
    package = tomllib.loads((crate / "Cargo.toml").read_text())["package"]["name"]
    toolchain = tomllib.loads((crate / "rust-toolchain.toml").read_text())["toolchain"]["channel"]
    env = dict(os.environ, CARGO_TARGET_DIR=str(target), RUSTUP_TOOLCHAIN=toolchain)
    flags = ["--locked", "--offline", "--release", "--manifest-path", crate / "Cargo.toml"]
    inputs = set(json.loads((target / "compiler-inputs.json").read_bytes()))

    def build():
        if (ROOT / archive).exists():
            subprocess.run(["cargo", "clean", "-p", package, "--release", "--manifest-path", crate / "Cargo.toml"],
                           cwd=crate, env=env, check=True)
            if (ROOT / archive).exists():
                raise ValueError("package clean retained the candidate archive")
        subprocess.run(["cargo", "build", *flags], cwd=crate, env=env, check=True)
        if rust_inputs(ROOT / archive) != {source / name for name in inputs}:
            raise ValueError("compiler-selected sources differ from the release")
        return digest(ROOT / archive)

    if build() != sha:
        raise ValueError("control build differs from the release archive")
    with tempfile.TemporaryDirectory() as tmp:
        diagnostics = Path(tmp) / "unused.jsonl"
        with diagnostics.open("w") as stream:
            cmd = ["cargo", "rustc", "--message-format=json", "--lib", *flags,
                   "--", "-A", "warnings", "--force-warn", "dead_code"]
            with subprocess.Popen(cmd, cwd=crate, env=env, stdout=subprocess.PIPE, text=True) as child:
                for line in child.stdout:
                    record = json.loads(line)
                    if record.get("reason") == "compiler-message" and record["target"]["src_path"] == str(crate / "lib.rs"):
                        print(json.dumps(record["message"]), file=stream)
                if child.wait():
                    raise ValueError("Cargo could not produce declaration diagnostics")
        selector = ROOT / "work/analysis/private-inlines-linux/release/foreign-declarations"
        report = verify_declarations(crate, inputs, diagnostics, selector, sha, build, allow_empty=True)
    (target / "declaration-proof.json").write_text(json.dumps(report, sort_keys=True) + "\n")


def trial(link, archive, *, publish=False, pinned=None, log=None):
    source, base = layout(archive)
    sha = link["source_library_sha256"][str(archive)]
    if digest(ROOT / archive) != sha:
        raise ValueError("archive differs from release")
    inputs = {str(p.relative_to(source)) for p in rust_inputs(ROOT / archive)}
    parent = link.get("linked_private_inline_proofs", {}).get(str(archive))
    second = link.get("linked_second_inline_proofs", {}).get(str(archive))
    with tempfile.TemporaryDirectory(dir=ROOT / "work/analysis") as tmp:
        crate, target = Path(tmp) / "source", Path(tmp) / "target"
        shutil.copytree(ROOT / source, crate, ignore=shutil.ignore_patterns("target"))
        target.mkdir()
        if parent:
            receipt = (ROOT / archive).with_name(parent["file"])
            if digest(receipt) != parent["sha256"]:
                raise ValueError("previous receipt differs from release")
            record = json.loads(receipt.read_bytes())
            if record["archive_sha256"] != sha:
                raise ValueError("previous receipt belongs to another archive")
            apply_receipt(crate, record, inputs)
        if second:
            record = read_second_layer(ROOT / archive, archive, second, parent, sha)
            apply_receipt(crate, record["second_layer"], inputs)
        for directory in (crate, target):
            (directory / ".rustbox-foreign-trial").write_text(sha)
        (target / "compiler-inputs.json").write_text(json.dumps(sorted(inputs)))
        subprocess.run(["docker", "run", "--rm", "--network", "none", "--platform", "linux/amd64",
                        "--workdir", "/work", "-v", f"{ROOT}:/work:ro", "--tmpfs", "/work/.git:ro",
                        "-v", "rustbox-pointer-cargo-registry:/root/.cargo/registry:ro",
                        "-v", f"{crate}:/work/{source}", "-v", f"{target}:/work/{base}",
                        "rustbox-e2fsprogs:2026-11-24", "python3", "-B",
                        "/work/scripts/check_cargo_foreign_declarations.py", "--mounted", str(archive), sha],
                       stdout=log, stderr=subprocess.STDOUT if log else None, check=True)
        if digest(target / "release" / archive.name) != sha:
            raise ValueError("candidate archive differs after compilation")
        report = json.loads((target / "declaration-proof.json").read_bytes())
        if any(digest(crate / n) != v for n, v in report["declarations"]["sources"].items()):
            raise ValueError("candidate sources differ from the proof")
        report.update(archive=str(archive), archive_sha256=sha, parent=parent, second=second)
        if pinned and not report["declarations"]["ranges"]:
            raise ValueError("pinned declaration selection rebuilt with no eligible declarations")
        if publish and report["declarations"]["ranges"]:
            publish_verified(ROOT / archive, target / "release" / archive.name, report, pinned)
        return report


def prepare_release():
    selected = json.loads(MANIFEST.read_bytes())
    second = json.loads((ROOT / "batches/multicall-second-inline-proofs.json").read_bytes())

    def prepare(item):
        name, record = item
        relative = Path(name)
        layout(relative)
        if record != selection(relative, record["sha256"]):
            raise ValueError(f"invalid Cargo declaration receipt: {name}")
        package = re.sub(r"-[0-9].*$", "", relative.parts[2])
        index = ROOT / f"work/analysis/{package}-cargo-inline-proofs.json"
        parents = json.loads(index.read_bytes()) if index.is_file() else {}
        archive = ROOT / relative
        link = {"source_library_sha256": {name: digest(archive)}, "linked_private_inline_proofs": parents,
                "linked_second_inline_proofs": second}
        if not archive.with_name(record["file"]).is_file():
            trial(link, relative, publish=True, pinned=record)
        read_proof(link, relative, record)

    with ThreadPoolExecutor(max_workers=3) as workers:
        list(workers.map(prepare, selected.items()))


def enroll(link, reports, existing):
    staged = staged_archives(link)
    expected = {name: record for name, record in link.get("linked_foreign_declaration_proofs", {}).items()
                if name not in staged}
    if expected != existing:
        raise ValueError("start from the Cargo declaration manifest in the selected release")
    seen = {}
    for path in reports:
        report = json.loads(path.read_bytes())
        relative = Path(report["archive"])
        layout(relative)
        validate_proof(link, relative, report, allow_empty=True)
        if digest(ROOT / relative) != report["archive_sha256"]:
            raise ValueError(f"archive differs from selected link: {relative}")
        data = (json.dumps(report, sort_keys=True) + "\n").encode()
        record = selection(relative, hashlib.sha256(data).hexdigest())
        if seen.setdefault(relative, record) != record:
            raise ValueError(f"conflicting declaration reports for {relative}")
        if not report["declarations"]["ranges"]:
            if str(relative) in expected:
                raise ValueError(f"empty report conflicts with the pinned selection: {relative}")
            continue
        if expected.setdefault(str(relative), record) != record:
            raise ValueError(f"conflicting declaration selections for {relative}")
    return expected


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mounted", nargs=2, metavar=("ARCHIVE", "SHA"), help=argparse.SUPPRESS)
    parser.add_argument("--prepare", action="store_true", help="prepare the pinned Cargo declaration selections")
    parser.add_argument("--publish", action="store_true", help="retain the rebuilt archive and its immutable receipt")
    parser.add_argument("--enroll", type=Path, nargs="+", metavar="REPORT", help="pin verified trial reports for the next release")
    parser.add_argument("link", nargs="?", type=Path)
    parser.add_argument("archive", nargs="?", type=Path)
    parser.add_argument("output", nargs="?", type=Path)
    args = parser.parse_args()
    if args.prepare:
        if args.mounted or args.link or args.archive or args.output or args.publish or args.enroll:
            parser.error("--prepare takes no other arguments")
        prepare_release()
    elif args.enroll:
        if not args.link or args.archive or args.output or args.mounted or args.publish:
            parser.error("use LINK --enroll REPORT ...")
        records = enroll(json.loads(args.link.read_bytes()), args.enroll, json.loads(MANIFEST.read_bytes()))
        with tempfile.NamedTemporaryFile(mode="w", dir=MANIFEST.parent, delete=False) as pending:
            print(json.dumps(records, sort_keys=True, indent=2), file=pending)
        staged = Path(pending.name)
        staged.chmod(MANIFEST.stat().st_mode & 0o777)
        staged.replace(MANIFEST)
    elif args.mounted:
        if args.link or args.archive or args.output or args.publish:
            parser.error("unexpected arguments to the isolated compiler")
        compile_trial(Path(args.mounted[0]), args.mounted[1])
    else:
        if not (args.link and args.archive and args.output) or args.output.exists():
            parser.error("provide LINK ARCHIVE and a new OUTPUT file")
        link = json.loads(args.link.read_bytes())
        pinned = link.get("linked_foreign_declaration_proofs", {}).get(str(args.archive))
        proof = trial(link, args.archive, publish=args.publish, pinned=pinned)
        with args.output.open("x") as stream:
            print(json.dumps(proof, sort_keys=True), file=stream)
        print(json.dumps({k: proof[k] for k in ("archive", "declarations_removed", "raw_pointer_type_tokens_removed")}))
