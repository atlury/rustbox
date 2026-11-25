"""Verify unused foreign declarations against the staged, linked E2fsprogs archive."""
# SPDX-License-Identifier: 0BSD
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile

from check_cargo_private_inlines import ROOT, digest
from check_next_inline_layer import apply_receipt, read_second_layer
from inline_source_layout import pad_removed_items
from prune_private_inlines import replay


def selection(archive, sha):
    return {"file": archive.with_suffix(f".foreign-{sha}.json").name, "sha256": sha}


def read_proof(link, relative, selected, repository=ROOT):
    archive = repository / relative
    if selected != selection(archive, selected["sha256"]):
        raise ValueError(f"unexpected foreign declaration receipt name: {relative}")
    data = archive.with_name(selected["file"]).read_bytes()
    report = json.loads(data)
    layer = report["declarations"]
    expected = link["source_library_sha256"][str(relative)]
    if (hashlib.sha256(data).hexdigest() != selected["sha256"] or report["archive"] != str(relative)
            or report["archive_sha256"] != expected or layer["archive_sha256"] != expected
            or report["parent"] != link["linked_private_inline_proofs"][str(relative)]
            or report["second"] != link.get("linked_second_inline_proofs", {}).get(str(relative))
            or not layer["ranges"] or layer["ranges"].keys() != layer["sources"].keys()):
        raise ValueError(f"foreign declaration receipt differs from its release inputs: {relative}")
    return report


def prove(link, relative, scratch, repository=ROOT):
    from audit_linked_pointers import crate_for
    from check_e2fsprogs_private_inlines import compiler

    archive = repository / relative
    name = archive.parent.name
    if (relative.parts[:2] != ("work", "analysis") or relative.parts[3:5] != ("program-translations", "rustbox-e2fsprogs-shared")
            or len(relative.parts) != 7 or ".." in relative.parts or archive.name != f"lib{name}_audit.a"):
        raise ValueError(f"unexpected shared E2fsprogs archive: {relative}")
    expected = link["source_library_sha256"][str(relative)]
    manifest = json.loads(archive.with_suffix(".sources.json").read_bytes())
    if digest(archive) != expected or manifest["archive_sha256"] != expected:
        raise ValueError("E2fsprogs archive differs from the selected link")
    source = crate_for(archive, scratch)
    inputs = set(manifest["sources"])
    if any(digest(source / name) != sha for name, sha in manifest["sources"].items()):
        raise ValueError("staged input differs from the compiler manifest")
    parent = link["linked_private_inline_proofs"][str(relative)]
    receipt = archive.with_name(parent["file"])
    parent_proof = json.loads(receipt.read_bytes())
    if digest(receipt) != parent["sha256"] or parent_proof["archive_sha256"] != expected:
        raise ValueError("E2fsprogs parent receipt differs from the selected link")
    apply_receipt(source, parent_proof, inputs)
    second = link.get("linked_second_inline_proofs", {}).get(str(relative))
    if second:
        record = read_second_layer(archive, relative, second, parent, expected)
        apply_receipt(source, record["second_layer"], inputs)

    deps = archive.parents[2] / "cargo-target" / name / "release/deps"
    rustc = [*compiler(source, deps, scratch, "/rustbox-e2fsprogs"), "--crate-type=staticlib"]
    staged = scratch / archive.name
    depfile = scratch / "compiler.d"

    def build():
        staged.unlink(missing_ok=True)
        depfile.unlink(missing_ok=True)
        subprocess.run([*rustc, "--cap-lints=allow", f"--emit=link,dep-info={depfile}",
                        "lib.rs", "-o", staged], cwd=source, check=True)
        rule = depfile.read_text().splitlines()[0].split(": ", 1)[1]
        if {p for p in shlex.split(rule) if p.endswith(".rs")} != inputs:
            raise ValueError("compiler-selected input list changed")
        return digest(staged)

    if build() != expected:
        raise ValueError("control build differs from the released E2fsprogs archive")
    diagnostics = scratch / "rustc.jsonl"
    with diagnostics.open("wb") as stream:
        subprocess.run([*rustc, "--emit=metadata", "-A", "warnings", "--force-warn", "dead_code",
                        "--error-format=json", "lib.rs", "-o", scratch / "engine.rmeta"],
                       cwd=source, stderr=stream, check=True)
    selector = repository / "work/analysis/private-inlines-linux/release/foreign-declarations"
    with diagnostics.open("rb") as stream:
        ranges = json.loads(subprocess.check_output([selector], cwd=source, stdin=stream))
    if not ranges or not ranges.keys() <= inputs:
        raise ValueError("expected declarations in compiler-selected files")
    originals = {name: (source / name).read_bytes() for name in ranges}
    removed = replay(source, ranges)
    layout = "lines"
    if build() != expected:
        pad_removed_items(source, ranges, originals)
        layout = "byte_offsets"
        if build() != expected:
            raise ValueError("declaration removal changed the archive")
    proof = {"archive_sha256": expected, "ranges": ranges, "sources": {n: digest(source / n) for n in ranges},
             "source_layout": layout}
    return {"archive": str(relative), "archive_sha256": expected, "parent": parent, "second": second,
            "selector_sha256": digest(selector), "declarations_removed": sum(map(len, ranges.values())),
            "raw_pointer_type_tokens_removed": removed,
            "source_bytes_removed": sum(len(data) - (source / n).stat().st_size for n, data in originals.items()),
            "declarations": proof}, staged


def publish(link, relative, pinned=None, repository=ROOT):
    archive = repository / relative
    with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory(dir=archive.parent) as out:
        report, staged = prove(link, relative, Path(tmp), repository)
        data = (json.dumps(report, sort_keys=True) + "\n").encode()
        selected = selection(archive, hashlib.sha256(data).hexdigest())
        if pinned is not None and pinned != selected:
            raise ValueError(f"rebuilt declaration proof differs from release: {relative}")
        pending = Path(out)
        receipt = pending / selected["file"]
        receipt.write_bytes(data)
        candidate = pending / archive.name
        shutil.copyfile(staged, candidate)
        if digest(candidate) != link["source_library_sha256"][str(relative)]:
            raise ValueError(f"staged archive changed: {relative}")
        candidate.replace(archive)
        receipt.replace(archive.with_name(receipt.name))
        return selected


def staged_archives(link):
    return {name for name in link["linked_private_inline_proofs"]
            if Path(name).parent.parent.name == "rustbox-e2fsprogs-shared"}


def prepare_release(repository, source_hashes, parents, second):
    selected = json.loads((repository / "batches/e2fsprogs-foreign-declarations.json").read_bytes())
    link = {"source_library_sha256": source_hashes, "linked_private_inline_proofs": parents,
            "linked_second_inline_proofs": second}
    if not selected.keys() <= staged_archives(link) & source_hashes.keys():
        raise ValueError("declaration manifest contains an unlinked archive")

    def prepare(item):
        name, record = item
        relative = Path(name)
        if record != selection(relative, record["sha256"]):
            raise ValueError(f"invalid declaration receipt name: {name}")
        if not (repository / relative).with_name(record["file"]).exists():
            publish(link, relative, record, repository)
        read_proof(link, relative, record, repository)

    with ThreadPoolExecutor(max_workers=3) as workers:
        list(workers.map(prepare, selected.items()))
    return selected


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("link_report", type=Path)
    parser.add_argument("output", type=Path, help="new directory for verified archive selections")
    parser.add_argument("--jobs", type=int, default=2)
    args = parser.parse_args()
    if args.jobs < 1:
        parser.error("--jobs must be positive")
    link = json.loads(args.link_report.read_bytes())
    args.output.mkdir()
    archives = sorted(staged_archives(link))
    if not archives:
        parser.error("the selected link has no staged E2fsprogs archives")

    def build(name):
        path = Path(name)
        selected = publish(link, path, link.get("linked_foreign_declaration_proofs", {}).get(name))
        report = read_proof(link, path, selected)
        (args.output / (path.stem + ".json")).write_text(json.dumps({name: selected}, indent=2) + "\n")
        print(f"{path.parent.name}: {report['raw_pointer_type_tokens_removed']} raw-pointer types", flush=True)
        return name, selected

    with ThreadPoolExecutor(max_workers=args.jobs) as workers:
        records = dict(workers.map(build, archives))
    (args.output / "manifest.json").write_text(json.dumps(records, sort_keys=True, indent=2) + "\n")
