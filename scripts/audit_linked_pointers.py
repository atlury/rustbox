#!/usr/bin/env python3
"""Measure Rust sources of applet archives selected by a Rustbox Linux link report."""
# SPDX-License-Identifier: 0BSD

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import shlex
import shutil
import tempfile

from check_e2fsprogs_dirhash_arrays import borrow_arrays, source_list_digest
from e2fsprogs_dirhash_archives import candidate_path, control_view, dirhash_parent
from e2fsprogs_hangul import replace_hangul
from build_iproute2_bridge import stage as stage_bridge
from build_e2fsprogs_checksums import CONSUMERS, SHARED_SOURCES, stage as stage_checksum
from check_next_inline_layer import apply_receipt, read_second_layer
from e2fsprogs_foreign_declarations import read_proof as read_declaration_proof

ROOT = Path(__file__).resolve().parents[1]
METRICS = {
    "raw_pointer_type_tokens": re.compile(rb"\*(?:mut|const)\b"),
    "raw_borrows": re.compile(rb"&raw\s+(?:mut|const)\b"),
    "as_ptr_calls": re.compile(rb"\.as_(?:mut_)?ptr\s*\("),
    "slices_from_raw_parts": re.compile(rb"\bfrom_raw_parts(?:_mut)?\s*\("),
}


def cleanup_name(archive):
    return archive.stem.removeprefix("lib").removesuffix("_audit")


def crate_for(archive, temporary):
    if "target" in archive.parts:
        return archive.parents[2]
    if archive.parent.name == "rustbox-bridge":
        engine = temporary / "bridge"
        shutil.copytree(archive.parents[1] / "bridge/bridge-final", engine)
        stage_bridge(engine, pilot=False)
        return engine
    if archive.parent.parent.name in ("rustbox-checksums", "rustbox-e2fsprogs-shared"):
        name = archive.parent.name
        engine = temporary / name
        shutil.copytree(archive.parents[2] / name / f"{name}-final", engine,
                        ignore=shutil.ignore_patterns("target"))
        stage_checksum(engine, share_bitcount=archive.parent.parent.name == "rustbox-e2fsprogs-shared")
        return engine
    target = next(p for p in archive.parents if p.name == "cargo-target")
    name = archive.name.removeprefix("lib").removesuffix("_audit.a")
    suffix = "stable" if archive.parent == target / "release" else "final"
    return target.parent / name / f"{name}-{suffix}"


def measure_layer(crate, files, proof, item_count="private_functions_removed"):
    inputs = {str(file.relative_to(crate)) for file in files}
    if not set(proof["ranges"]) <= inputs:
        raise ValueError("unexpected compiler input in cleanup")
    paths = [crate / name for name in proof["ranges"]]
    size = sum(path.stat().st_size for path in paths)
    removed = apply_receipt(crate, proof, inputs)
    files.update({crate / name: checksum for name, checksum in proof["sources"].items()})
    stats = {"raw_pointer_type_tokens_removed": removed,
             "source_bytes_removed": size - sum(path.stat().st_size for path in paths),
             item_count: sum(map(len, proof["ranges"].values())),
             "changed_files": len(paths)}
    for field in ("source_layout", "source_directory"):
        if field in proof:
            stats[field] = proof[field]
    return stats


def audit(link, temporary, inspect_source=None):
    fixed_arrays = link.get("e2fsprogs_dirhash_arrays", {})
    link = control_view(link)
    array_counts = {}
    hangul_counts = {}
    packages = {}
    unique = {}
    measured = Counter()
    excluded = []
    cleanups = {}
    proofs = link.get("linked_private_inline_proofs", link.get("e2fsprogs_inline_proofs", {}))
    second = link.get("linked_second_inline_proofs", {})
    second_cleanups = {}
    foreign = link.get("linked_foreign_declaration_proofs", {})
    declarations = {}
    if not second.keys() <= proofs.keys() & link["source_library_sha256"].keys():
        raise ValueError("second-layer receipt has no linked parent archive")
    for name, expected in sorted(link["source_library_sha256"].items()):
        path = Path(name)
        shared_object = path.name in SHARED_SOURCES and path.parent.name in ("rustbox-checksums", "rustbox-e2fsprogs-shared")
        if path.is_absolute() or (path.suffix != ".a" and not shared_object):
            excluded.append(name)
            continue
        archive = ROOT / path
        with archive.open("rb") as stream:
            hasher = hashlib.sha256()
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                hasher.update(chunk)
            if hasher.hexdigest() != expected:
                raise ValueError(f"archive differs from link report: {name}")
        crate = ROOT if shared_object else crate_for(archive, temporary)
        if not shared_object and not (crate / "Cargo.toml").is_file():
            raise ValueError(f"archive has no finalized source crate: {name}")
        package = path.relative_to("work/analysis").parts[0]
        tally = packages.setdefault(package, Counter())
        tally["standalone_objects" if shared_object else "archives"] += 1
        if shared_object or archive.parent.name == "rustbox-bridge" or archive.parent.parent.name in (
                "rustbox-checksums", "rustbox-e2fsprogs-shared"):
            manifest = json.loads(archive.with_suffix(".sources.json").read_text())
            if manifest["archive_sha256"] != expected:
                raise ValueError(f"stale compiler source list: {name}")
            files = {crate / name: sha for name, sha in manifest["sources"].items()}
        else:
            deps = archive.with_suffix(".d").read_text().splitlines()[0].split(": ", 1)[1]
            files = {ROOT / Path(name).relative_to("/work"): None
                     for name in shlex.split(deps) if name.endswith(".rs")}
        if name in proofs or name in foreign:
            if not crate.is_relative_to(temporary):
                original = crate
                crate = temporary / ("cargo-" + archive.stem)
                copied = {}
                for source_path, sha in files.items():
                    destination = crate / source_path.relative_to(original)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source_path, destination)
                    copied[destination] = sha
                files = copied
            crate.relative_to(temporary)
            engine_name = cleanup_name(archive)
        if selected := proofs.get(name):
            proof_file = archive.with_name(selected["file"])
            data = proof_file.read_bytes()
            if hashlib.sha256(data).hexdigest() != selected["sha256"]:
                raise ValueError(f"pruning evidence differs from link report: {name}")
            proof = json.loads(data)
            if (proof["archive_sha256"] != expected or set(proof["ranges"]) != set(proof["sources"])
                    or not {crate / n for n in proof["sources"]} <= files.keys()):
                raise ValueError(f"invalid private-inline provenance: {name}")
            if engine_name in cleanups:
                raise ValueError(f"duplicate cleanup evidence for {engine_name}")
            cleanups[engine_name] = measure_layer(crate, files, proof)
            if name in second:
                report = read_second_layer(archive, path, second[name], selected, expected)
                layer = report["second_layer"]
                if layer.get("source_directory") != proof.get("source_directory"):
                    raise ValueError("second-layer source scope differs from parent")
                stats = measure_layer(crate, files, layer)
                if any(stats[key] != report[key] for key in ("raw_pointer_type_tokens_removed", "private_functions_removed")):
                    raise ValueError("second-layer totals differ from independent source replay")
                second_cleanups[engine_name] = stats
        if name in foreign:
            report = read_declaration_proof(link, path, foreign[name])
            stats = measure_layer(crate, files, report["declarations"], "declarations_removed")
            if any(stats[key] != report[key] for key in (
                    "raw_pointer_type_tokens_removed", "declarations_removed", "source_bytes_removed")):
                raise ValueError("foreign declaration totals differ from independent source replay")
            declarations[engine_name] = stats
        linked_path = path
        source_digests = {}
        if record := fixed_arrays.get(name):
            linked_path = candidate_path(path, record["candidate_sha256"])
            if hashlib.sha256((ROOT / linked_path).read_bytes()).hexdigest() != record["candidate_sha256"]:
                raise ValueError(f"changed directory hash linker input: {linked_path}")
            module, = [f for f in files if f.as_posix().endswith("/lib/ext2fs/dirhash.rs")]
            original = module.read_bytes()
            if (str(module.relative_to(crate)) != record["module"]
                    or hashlib.sha256(original).hexdigest() != record["module_before"]):
                raise ValueError("directory hash source differs from the verified control")
            accesses = borrow_arrays(module)
            if accesses != record["raw_offset_accesses_replaced"]:
                raise ValueError("directory hash conversion did not explain the pointer accesses")
            files[module] = record["module_after"]
            pointer = METRICS["raw_pointer_type_tokens"]
            removed = len(pointer.findall(original)) - len(pointer.findall(module.read_bytes()))
            array_counts[engine_name] = {"raw_pointer_type_tokens_removed": removed,
                                         "raw_offset_accesses_replaced": accesses, "archive": str(linked_path)}
            if layer := record.get("hangul"):
                nls, = [f for f in files if f.as_posix().endswith("/lib/ext2fs/nls_utf8.rs")]
                observed = replace_hangul(nls)
                if (str(nls.relative_to(crate)) != layer["module"]
                        or any(layer[key] != value for key, value in observed.items())):
                    raise ValueError(f"Hangul compiler source differs from its receipt: {name}")
                files[nls] = observed["module_after"]
                hangul_counts[engine_name] = observed["raw_pointer_type_tokens_removed"]
        root_module = ROOT / f"compat/e2fsprogs/{SHARED_SOURCES[archive.name]}" if shared_object else crate / "lib.rs"
        if root_module not in files:
            raise ValueError(f"unexpected compiler inputs for {archive}")
        for file, source_sha in files.items():
            file.relative_to(crate)
            data = file.read_bytes()
            digest = hashlib.sha256(data).digest()
            if source_sha and digest.hex() != source_sha:
                raise ValueError(f"restaged source differs from linked version: {file.name}")
            if digest not in unique:
                unique[digest] = Counter({k: len(regex.findall(data)) for k, regex in METRICS.items()})
            if name in fixed_arrays:
                source_digests[str(file.relative_to(crate))] = digest.hex()
            tally.update(unique[digest])
            if inspect_source is not None and not shared_object:
                inspect_source(linked_path, digest, data)
            tally["files"] += 1
        if name in fixed_arrays and source_list_digest(source_digests) != fixed_arrays[name]["compiler_sources_sha256"]:
            raise ValueError(f"directory hash compiler inputs differ from the candidate: {name}")
        if record and (layer := record.get("hangul")):
            source_digests[layer["module"]] = layer["module_before"]
            if source_list_digest(source_digests) != layer["parent_sources_sha256"]:
                raise ValueError(f"Hangul parent source list differs from the directory hash release: {name}")
    if len(array_counts) != len(fixed_arrays):
        raise ValueError("directory hash conversion outside the measured archive set")
    if len(second_cleanups) != len(second):
        raise ValueError("second-layer archive was outside the linked source inventory")
    if len(declarations) != len(foreign):
        raise ValueError("foreign declaration proof was outside the linked source inventory")
    for tally in packages.values():
        measured.update(tally)
    distinct = Counter()
    for counts in unique.values():
        distinct.update(counts)
    return {"binary_sha256": link["binary"]["sha256"], "all": measured,
            "unique_files": len(unique), "counting_identical_files_once": distinct,
            "packages": packages, "non_applet_archive_inputs": excluded,
            **({"byte_identical_inline_cleanups": cleanups} if cleanups else {}),
            **({"byte_identical_second_inline_cleanups": second_cleanups} if second_cleanups else {}),
            **({"hangul_pointer_types_removed": hangul_counts} if hangul_counts else {}),
            **({"fixed_array_conversions": array_counts} if array_counts else {}),
            **({"byte_identical_foreign_declarations": declarations} if declarations else {})}


RECEIPT_SETS = (("linked_private_inline_proofs", "byte_identical_inline_cleanups"),
                ("linked_second_inline_proofs", "byte_identical_second_inline_cleanups"),
                ("linked_foreign_declaration_proofs", "byte_identical_foreign_declarations"))


def added_receipts(previous_link, link):
    """Require identical link fields and retain all earlier parent and child receipts."""
    fields = {field for field, _ in RECEIPT_SETS}
    for field in (previous_link.keys() | link.keys()) - fields:
        if field not in previous_link or field not in link or previous_link[field] != link[field]:
            raise ValueError(f"release field changed during private-helper cleanup: {field}")
    added = set()
    for field in fields:
        before, after = previous_link.get(field, {}), link.get(field, {})
        for archive, receipt in before.items():
            if after.get(archive) != receipt:
                raise ValueError(f"existing cleanup receipt changed for {archive}")
        added.update(after.keys() - before.keys())
    if not link.get("linked_second_inline_proofs", {}).keys() <= link.get("linked_private_inline_proofs", {}).keys():
        raise ValueError("second-layer receipt has no parent")
    return added


def check_added_cleanups(previous_link, link, previous, current):
    """Account for each package delta when adding receipts to an otherwise identical release."""
    added_receipts(previous_link, link)
    deltas = Counter()
    for field, inventory_field in RECEIPT_SETS:
        receipts = current.get(inventory_field, {})
        for archive in link.get(field, {}).keys() - previous_link.get(field, {}).keys():
            path = Path(archive)
            package = path.relative_to("work/analysis").parts[0]
            deltas[package] += receipts[cleanup_name(path)]["raw_pointer_type_tokens_removed"]

    for package, tally in previous["packages"].items():
        updated = current["packages"][package]
        if package not in deltas and updated != tally:
            raise ValueError(f"unrelated package inventory changed: {package}")
        if tally["raw_pointer_type_tokens"] - updated["raw_pointer_type_tokens"] != deltas[package]:
            raise ValueError(f"cleanup receipts do not explain the {package} pointer count")
    if previous["all"]["raw_pointer_type_tokens"] - current["all"]["raw_pointer_type_tokens"] != sum(deltas.values()):
        raise ValueError("cleanup receipts do not explain the linked pointer count")


def check_dirhash_conversion(before_link, after_link, before, after):
    parents = before_link.get("e2fsprogs_dirhash_arrays", {})
    records = after_link.get("e2fsprogs_dirhash_arrays", {})
    if not records:
        raise ValueError("missing post-conversion archives")
    if parents:
        if any("hangul" not in row for row in records.values()) or {
            name: dirhash_parent(row) for name, row in records.items()
        } != parents:
            raise ValueError("Hangul archives did not retain every previous directory hash receipt")
    elif any("hangul" in row for row in records.values()):
        raise ValueError("missing directory hash parents for the Hangul conversion")
    controls = control_view(after_link)
    before_link = control_view(before_link)
    for key in before_link.keys() | controls.keys():
        if key in {"binary", "e2fsprogs_dirhash_arrays"}:
            continue
        if key not in before_link or key not in controls or before_link[key] != controls[key]:
            raise ValueError(f"unrelated directory hash release field changed: {key}")
    if before_link["binary"]["dynamic_needed"] != after_link["binary"]["dynamic_needed"]:
        raise ValueError("directory hash conversion changed runtime dependencies")
    changes = after["fixed_array_conversions"]
    if set(changes) != set(CONSUMERS) or any(row["raw_pointer_type_tokens_removed"] != 10
            or row["raw_offset_accesses_replaced"] != 40 for row in changes.values()):
        raise ValueError("expected both fixed-array conversions in all 13 E2fsprogs engines")
    expected = {"raw_pointer_type_tokens": 10 * len(changes), "raw_borrows": 4 * len(changes)}
    if parents:
        if after.get("hangul_pointer_types_removed") != {engine: 10 for engine in CONSUMERS}:
            raise ValueError("expected the live Hangul conversion in all 13 engines")
        expected = {"raw_pointer_type_tokens": 10 * len(changes)}
    if before["packages"].keys() != after["packages"].keys():
        raise ValueError("package set changed during directory hash conversion")
    for package, counts in before["packages"].items():
        delta = Counter(counts)
        delta.subtract(after["packages"][package])
        difference = {metric: value for metric, value in delta.items() if value}
        if difference != (expected if package.startswith("e2fsprogs-") else {}):
            raise ValueError(f"unexplained source delta for {package}: {difference}")


def measure(link, inspect_source=None):
    with tempfile.TemporaryDirectory() as temp:
        return audit(link, Path(temp), inspect_source)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("link_report", type=Path)
    previous = parser.add_mutually_exclusive_group()
    previous.add_argument("--verify-dirhash-from", type=Path, metavar="CONTROL",
                          help="verify 13 live fixed-array conversions against the previous production link")
    previous.add_argument("--verify-cleanup-from", type=Path, metavar="PREVIOUS_LINK",
                        help="replay both releases and check the reduction against their added cleanup receipts")
    args = parser.parse_args()
    link_bytes = args.link_report.read_bytes()
    link = json.loads(link_bytes)
    current = measure(link)
    current["link_report_sha256"] = hashlib.sha256(link_bytes).hexdigest()
    if args.verify_cleanup_from:
        previous_link = json.loads(args.verify_cleanup_from.read_bytes())
        check_added_cleanups(previous_link, link, measure(previous_link), current)
    if args.verify_dirhash_from:
        previous_link = json.loads(args.verify_dirhash_from.read_bytes())
        check_dirhash_conversion(previous_link, link, measure(previous_link), current)
    if args.link_report.read_bytes() != link_bytes:
        raise ValueError("selected link report changed during the inventory")
    print(json.dumps(current, indent=2, sort_keys=True))
