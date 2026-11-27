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

from cargo_archive_pilot import verify_source_substitution
import curl_manual
import curl_manual_archive
from tar_timespec_archive import selection as tar_timestamps
from bison_length_archive import selection as bison_lengths
from lz4_dictionary_archive import selection as lz4_dictionary
import stage_routing_protocol_archives as routing_protocols
from build_tar_timespec_pilot import MODULE as TIMESTAMP_MODULE, replace_timestamps
import share_stdio_layout
import verify_c_string_sources as native_strings
import iproute2_address_protocol_archive as address_protocols
import iproute2_route_name_archives as route_archives
from iproute2_route_names import replace_route_names, replace_netlink_protocols
from check_e2fsprogs_dirhash_arrays import borrow_arrays, source_list_digest
from e2fsprogs_dirhash_archives import candidate_path, control_view, prior_stage
from e2fsprogs_hangul import replace_hangul
from check_e2fsprogs_utf8_trie import replace_lookup
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


def audit(link, temporary, inspect_source=None, *, inspect_module=None, archive_pair=None, include_standalone_modules=False):
    final_hashes = link["source_library_sha256"]
    dictionary_record = link.get(lz4_dictionary.field, {}).get("pilot")
    dictionary_deltas = {}
    link = lz4_dictionary.parent_view(link)
    routing_records = link.get(routing_protocols.FIELD, {})
    routing_deltas = {}
    link = routing_protocols.parent_view(link)
    link_archive_hashes = link["source_library_sha256"]
    stdio_records = link.get("shared_stdio_layouts", {})
    stdio_deltas = {}
    va_records = link.get("shared_va_list_layouts", {})
    va_deltas = {}
    term_records = link.get("shared_ncurses_termtypes", {})
    term_deltas = {}
    literal_records = link.get("native_c_strings", {})
    literal_deltas = {}
    literal_tool = native_strings.syntax_tool() if literal_records else None
    length_record = link.get(bison_lengths.field, {}).get("pilot")
    length_deltas = {}
    link = bison_lengths.parent_view(link)
    timestamp_record = link.get(tar_timestamps.field, {}).get("pilot")
    timestamp_records = {tar_timestamps.key: timestamp_record} if timestamp_record else {}
    timestamp_deltas = {}
    link = tar_timestamps.parent_view(link)
    curl_record = link.get("curl_manual", {}).get("pilot")
    curl_records = {curl_manual_archive.KEY: curl_record} if curl_record else {}
    curl_deltas = {}
    link = curl_manual_archive.parent_view(link)
    fixed_arrays = link.get("e2fsprogs_dirhash_arrays", {})
    netlink_records = link.get("iproute2_netlink_protocols", {})
    netlink_deltas = {}
    route_records = link.get("iproute2_route_names", {})
    address_records = address_protocols.selected_records(link)
    link = address_protocols.control_view(control_view(link))
    address_deltas = {}
    route_deltas = {}
    array_counts = {}
    hangul_counts = {}
    trie_counts = {}
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
    hashes = link["source_library_sha256"]
    if archive_pair:
        original, selected_path = map(str, archive_pair)
        if original not in hashes or selected_path not in final_hashes:
            raise ValueError("requested Cargo archive lies outside the checked link")
        hashes = {original: hashes[original]}

        def for_key(records, key=original):
            return {key: records[key]} if key in records else {}

        proofs, second, foreign = map(for_key, (proofs, second, foreign))
        address_records, route_records, netlink_records, fixed_arrays, curl_records = map(
            for_key, (address_records, route_records, netlink_records, fixed_arrays, curl_records))
        timestamp_records = for_key(timestamp_records)
        if original != bison_lengths.key:
            length_record = None
        routing_records = {k: r for k, r in routing_records.items() if str(routing_protocols.candidate_path(r)) == selected_path}
        if original != lz4_dictionary.key:
            dictionary_record = None
        before_table = lz4_dictionary.key if dictionary_record else next(iter(routing_records), selected_path)
        stdio_records = for_key(stdio_records, before_table)
        literal_records = for_key(literal_records, before_table)
        va_records = for_key(va_records, selected_path)
        term_records = for_key(term_records, selected_path)
    if not second.keys() <= proofs.keys() & link["source_library_sha256"].keys():
        raise ValueError("second-layer receipt has no linked parent archive")
    for name, expected in sorted(hashes.items()):
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
        for records, archive_path, transform, deltas, relative_module in (
            (address_records, address_protocols.candidate_path, address_protocols.replace_table, address_deltas, address_protocols.MODULE),
            (route_records, route_archives.candidate_path, replace_route_names, route_deltas, address_protocols.MODULE),
            (netlink_records, route_archives.netlink_path, replace_netlink_protocols, netlink_deltas, address_protocols.MODULE),
            (timestamp_records, tar_timestamps.candidate_path, replace_timestamps, timestamp_deltas, TIMESTAMP_MODULE),
            (curl_records, curl_manual_archive.candidate_path, curl_manual.replace_manual, curl_deltas, curl_manual.MODULE),
        ):
            if name not in records:
                continue
            record = records[name]
            linked_path = archive_path(record)
            if hashlib.sha256((ROOT / linked_path).read_bytes()).hexdigest() != record["candidate_sha256"]:
                raise ValueError(f"archive differs from link evidence: {linked_path}")
            crate.relative_to(temporary)
            module = crate / relative_module
            sources = {str(f.relative_to(crate)): hashlib.sha256(f.read_bytes()).hexdigest() for f in files}
            original = module.read_bytes()
            replacement, changes = transform(original)
            verify_source_substitution(record, sources, changes, relative_module)
            deltas[name] = {k: len(regex.findall(original)) - len(regex.findall(replacement)) for k, regex in METRICS.items()}
            module.write_bytes(replacement)
            files[module] = changes["candidate_module_sha256"]
        if length_record and name == bison_lengths.key:
            linked_path = bison_lengths.candidate_path(length_record)
            if hashlib.sha256((ROOT / linked_path).read_bytes()).hexdigest() != length_record["candidate_sha256"]:
                raise ValueError("Bison archive differs from the source receipt")
            crate.relative_to(temporary)
            sources = {str(f.relative_to(crate)): hashlib.sha256(f.read_bytes()).hexdigest() for f in files}
            changes = native_strings.replay(sources, lambda module: (crate / module).read_bytes(),
                                           length_record, native_strings.syntax_tool("literal-lengths"), lengths=True)
            counts = Counter(dict.fromkeys(METRICS, 0))
            for module, replacement in changes.items():
                f = crate / module
                original = f.read_bytes()
                counts.update({k: len(regex.findall(original)) - len(regex.findall(replacement)) for k, regex in METRICS.items()})
                f.write_bytes(replacement)
                files[f] = hashlib.sha256(replacement).hexdigest()
            length_deltas[name] = dict(counts)
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
            for stage, transform, totals in (("hangul", replace_hangul, hangul_counts),
                                              ("trie", replace_lookup, trie_counts)):
                if stage not in record:
                    continue
                layer = record[stage]
                nls, = [f for f in files if f.as_posix().endswith("/lib/ext2fs/nls_utf8.rs")]
                if (str(nls.relative_to(crate)) != layer["module"]
                        or hashlib.sha256(nls.read_bytes()).hexdigest() != layer["module_before"]):
                    raise ValueError(f"{stage} compiler input differs from its receipt: {name}")
                observed = transform(nls)
                if any(layer[key] != value for key, value in observed.items()):
                    raise ValueError(f"{stage} conversion differs from its receipt: {name}")
                files[nls] = observed["module_after"]
                totals[engine_name] = observed["raw_pointer_type_tokens_removed"]
        root_module = ROOT / f"compat/e2fsprogs/{SHARED_SOURCES[archive.name]}" if shared_object else crate / "lib.rs"
        if root_module not in files:
            raise ValueError(f"unexpected compiler inputs for {archive}")
        stdio = stdio_records.get(str(linked_path))
        replacements = {}
        if stdio is not None:
            replacements = share_stdio_layout.replay(crate, files, stdio, linked_path, link_archive_hashes[str(linked_path)])
            stdio_deltas[str(linked_path)] = stdio["raw_pointer_types_removed"]
        def read_parent(module):
            path = crate / module
            return replacements[path] if path in replacements else path.read_bytes()

        literal = literal_records.get(str(linked_path))
        routing = routing_records.get(str(linked_path))
        dictionary = dictionary_record if name == lz4_dictionary.key else None
        table = routing or dictionary
        final_path = linked_path
        if routing:
            final_path = routing_protocols.candidate_path(routing)
        elif dictionary:
            final_path = lz4_dictionary.candidate_path(dictionary)
        if archive_pair and str(final_path) != selected_path:
            raise ValueError("Cargo origin does not yield the requested linked archive")
        va = va_records.get(str(final_path))
        term = term_records.get(str(final_path))
        if any(record is not None for record in (literal, table, va, term)):
            modules = [str(path.relative_to(crate)) for path in files]
            parent = {module: hashlib.sha256(read_parent(module)).hexdigest() for module in modules}
        if literal is not None:
            archive_sha = link_archive_hashes[str(linked_path)]
            if (literal["archive"] != str(linked_path) or literal["control_sha256"] != archive_sha
                    or literal["candidate_sha256"] != archive_sha):
                raise ValueError(f"C-string archive differs from the cold build: {linked_path}")

            changed = native_strings.replay(parent, read_parent, literal, literal_tool)
            replacements.update({crate / module: data for module, data in changed.items()})
            literal_deltas[str(linked_path)] = literal["c_string_literals"]
        if literal is not None and any(record is not None for record in (table, va, term)):
            parent.update({module: hashlib.sha256(data).hexdigest() for module, data in changed.items()})
        if table is not None:
            if routing:
                from build_routing_protocol_pilot import transform as replace_table
                deltas = routing_deltas
            else:
                from build_lz4_dictionary_pilot import transform as replace_table
                deltas = dictionary_deltas
            if hashlib.sha256((ROOT / final_path).read_bytes()).hexdigest() != table["candidate_sha256"]:
                raise ValueError(f"staged archive differs from its compiler receipt: {final_path}")
            module = table["module"]
            old = read_parent(module)
            new, facts = replace_table(old)
            verify_source_substitution(table, parent, facts, module)
            deltas[str(linked_path)] = {k: len(regex.findall(old)) - len(regex.findall(new))
                                        for k, regex in METRICS.items()}
            replacements[crate / module] = new
            parent[module] = facts["candidate_module_sha256"]
            linked_path = final_path
        for record_layout, kind, deltas in ((va, "va-list", va_deltas), (term, "termtype", term_deltas)):
            if record_layout is None:
                continue
            if kind == "termtype":
                from build_ncurses_termtype_layouts import substitute as share_layout
                if linked_path.name != "libncurses_6_6_normalized_audit.a":
                    raise ValueError("terminal layouts must belong to the selected ncurses archive")
            else:
                from build_va_list_layout_pilot import substitute as share_layout
            if (record_layout["archive"] != str(linked_path)
                    or record_layout["control_sha256"] != final_hashes[str(linked_path)]
                    or record_layout["candidate_sha256"] != record_layout["control_sha256"]):
                raise ValueError(f"{kind} archive differs from its cold build: {linked_path}")
            if (len(parent) != record_layout["compiler_selected_sources"]
                    or source_list_digest(parent) != record_layout["parent_sources_sha256"]):
                raise ValueError(f"{kind} parent sources differ from the cold build")
            options = {"modules": record_layout["reexporting_modules"]} if kind == "va-list" else {}
            changes, facts = share_layout(crate, parent, read_parent, **options)
            parent.update({module: hashlib.sha256(data).hexdigest() for module, data in changes.items()})
            if (any(record_layout[k] != v for k, v in facts.items())
                    or source_list_digest(parent) != record_layout["candidate_sources_sha256"]):
                raise ValueError(f"{kind} substitution differs from its verified compiler inputs")
            replacements.update({crate / module: data for module, data in changes.items()})
            deltas[str(linked_path)] = facts["raw_pointer_types_removed"]
        for file, source_sha in files.items():
            file.relative_to(crate)
            data = file.read_bytes()
            digest = hashlib.sha256(data).digest()
            if source_sha and digest.hex() != source_sha:
                raise ValueError(f"restaged source differs from linked version: {file.name}")
            if name in fixed_arrays:
                source_digests[str(file.relative_to(crate))] = digest.hex()
            if file in replacements:
                data = replacements[file]
                digest = hashlib.sha256(data).digest()
            if digest not in unique:
                unique[digest] = Counter({k: len(regex.findall(data)) for k, regex in METRICS.items()})
            tally.update(unique[digest])
            if inspect_source is not None and not shared_object:
                inspect_source(linked_path, digest, data)
            if inspect_module is not None and (include_standalone_modules or not shared_object):
                inspect_module(linked_path, file.relative_to(crate), digest, data)
            tally["files"] += 1
        if name in fixed_arrays and source_list_digest(source_digests) != fixed_arrays[name]["compiler_sources_sha256"]:
            raise ValueError(f"directory hash compiler inputs differ from the candidate: {name}")
        for stage in ("trie", "hangul"):
            if record and (layer := record.get(stage)):
                source_digests[layer["module"]] = layer["module_before"]
                if source_list_digest(source_digests) != layer["parent_sources_sha256"]:
                    raise ValueError(f"{stage} parent source list differs from its receipt: {name}")
    if bool(dictionary_record) != bool(dictionary_deltas):
        raise ValueError("LZ4 dictionary receipt outside the compiler inputs")
    if bool(length_record) != bool(length_deltas):
        raise ValueError("Bison length receipt outside the compiler inputs")
    if timestamp_records.keys() != timestamp_deltas.keys():
        raise ValueError("tar timestamp receipt outside linked compiler inputs")
    if routing_deltas.keys() != routing_records.keys():
        raise ValueError("routing protocol record lies outside the selected compiler inputs")
    if term_deltas.keys() != term_records.keys():
        raise ValueError("terminal layout receipt lies outside the selected archives")
    if va_deltas.keys() != va_records.keys():
        raise ValueError("variadic layout receipt lies outside the selected archives")
    if literal_deltas.keys() != literal_records.keys():
        raise ValueError("C-string receipt is outside the selected archive set")
    if stdio_deltas.keys() != stdio_records.keys():
        raise ValueError("stdio receipt is outside the selected archive set")
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
            **({"native_c_string_conversions": literal_deltas} if literal_deltas else {}),
            **({"routing_protocol_deltas": routing_deltas} if routing_deltas else {}),
            **({"shared_ncurses_termtype_deltas": term_deltas} if term_deltas else {}),
            **({"shared_va_list_layout_deltas": va_deltas} if va_deltas else {}),
            **({"shared_stdio_layout_deltas": stdio_deltas} if stdio_deltas else {}),
            **({"lz4_dictionary_deltas": dictionary_deltas} if dictionary_deltas else {}),
            **({"bison_length_deltas": length_deltas} if length_deltas else {}),
            **({"tar_timestamp_deltas": timestamp_deltas} if timestamp_deltas else {}),
            **({"curl_manual_deltas": curl_deltas} if curl_deltas else {}),
            **({"iproute2_netlink_protocol_deltas": netlink_deltas} if netlink_deltas else {}),
            **({"iproute2_route_name_deltas": route_deltas} if route_deltas else {}),
            **({"iproute2_address_protocol_deltas": address_deltas} if address_deltas else {}),
            **({"trie_pointer_types_removed": trie_counts} if trie_counts else {}),
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


def unicode_namespace(before, records, stage):
    """Predict the linker map from independently measured strong-symbol changes."""
    changes = json.loads((ROOT / "batches/e2fsprogs-unicode-symbols.json").read_bytes())[stage]
    if set(changes) != set(CONSUMERS):
        raise ValueError("incomplete Unicode symbol measurements")
    expected = before.copy()
    for name, row in records.items():
        engine = Path(name).parent.name
        change = changes[engine]
        added, = change["added"]
        component = {"hangul": "11hangul_leaf9decompose", "trie": "9utf8_trie6lookup"}[stage]
        symbol = rf"_ZN[0-9]+{re.escape(engine)}_audit3src[0-9a-zA-Z_]+8nls_utf8{component}17h[0-9a-f]{{16}}E"
        if (not re.fullmatch(symbol, added) or change["removed"] or added in before[engine]
                or change["before"] != row[stage]["parent_archive_sha256"]
                or change["after"] != row["candidate_sha256"]):
            raise ValueError(f"unexpected Unicode symbol change for {engine}")
        expected[engine] = sorted([*before[engine], added])
    return expected


def check_dirhash_conversion(before_link, after_link, before, after):
    parents = before_link.get("e2fsprogs_dirhash_arrays", {})
    records = after_link.get("e2fsprogs_dirhash_arrays", {})
    if not records:
        raise ValueError("missing post-conversion archives")
    stage = "trie" if any("trie" in row for row in records.values()) else "hangul"
    if parents:
        if any(stage not in row for row in records.values()) or {
            name: prior_stage(row, stage) for name, row in records.items()
        } != parents:
            raise ValueError(f"{stage} archives did not retain every preceding receipt")
    elif any("hangul" in row for row in records.values()):
        raise ValueError("missing directory hash parents for the Hangul conversion")
    controls = control_view(after_link)
    before_link = control_view(before_link)
    if parents:
        before_link = dict(before_link, e2fsprogs_namespaced_symbols=unicode_namespace(
            before_link["e2fsprogs_namespaced_symbols"], records, stage))
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
        if stage == "trie":
            if after.get("trie_pointer_types_removed") != {engine: 5 for engine in CONSUMERS}:
                raise ValueError("expected safe trie traversal in all 13 engines")
            expected = {"raw_pointer_type_tokens": 5 * len(changes), "raw_borrows": len(changes)}
    if before["packages"].keys() != after["packages"].keys():
        raise ValueError("package set changed during directory hash conversion")
    for package, counts in before["packages"].items():
        delta = Counter(counts)
        delta.subtract(after["packages"][package])
        difference = {metric: value for metric, value in delta.items() if value}
        if difference != (expected if package.startswith("e2fsprogs-") else {}):
            raise ValueError(f"unexplained source delta for {package}: {difference}")


def check_address_protocol_conversion(previous_link, link, before, after):
    previous_records = address_protocols.selected_records(previous_link)
    records = address_protocols.selected_records(link)
    if not previous_records.keys() < records.keys() or any(records[k] != v for k, v in previous_records.items()):
        raise ValueError("address-protocol conversion lost an existing archive or added no new one")
    control = address_protocols.control_view(link)
    previous_link = address_protocols.control_view(previous_link)
    added = {k: v for k, v in records.items() if k not in previous_records}
    check_archive_counts(previous_link, control, before, after, added, "iproute2_address_protocol_deltas")


def check_archive_counts(previous_link, control, before, after, added, delta_field):
    for field in (control.keys() | previous_link.keys()) - {"binary"}:
        if field not in control or field not in previous_link or control[field] != previous_link[field]:
            raise ValueError(f"archive substitution changed an unrelated link field: {field}")
    if control["binary"]["dynamic_needed"] != previous_link["binary"]["dynamic_needed"]:
        raise ValueError("archive substitution changed runtime dependencies")
    delta = Counter()
    for key, row in added.items():
        observed = after[delta_field][key]
        count_key = "raw_pointer_types_removed" if "raw_pointer_types_removed" in row else "raw_pointer_types_removed_in_pilot_module"
        if observed["raw_pointer_type_tokens"] != row[count_key]:
            raise ValueError(f"archive type reduction differs from the pilot for {key}")
        delta.update(observed)
    expected_total = Counter(before["all"])
    expected_total.subtract(delta)
    if dict(expected_total) != after["all"]:
        raise ValueError("archive substitutions do not explain the linked pointer inventory")
    changed, = {Path(key).relative_to("work/analysis").parts[0] for key in added}
    if before["packages"].keys() != after["packages"].keys():
        raise ValueError("package set changed during archive substitution")
    for package, stats in before["packages"].items():
        expected = Counter(stats)
        if package == changed:
            expected.subtract(delta)
        if dict(expected) != after["packages"][package]:
            raise ValueError(f"unexplained archive inventory change for {package}")


def check_identical_layer(previous, selected, before, after, field):
    previous_records = previous.get(field, {})
    records = selected[field]
    if (not previous_records.keys() <= records.keys() or previous_records == records
            or {k: v for k, v in previous.items() if k != field}
               != {k: v for k, v in selected.items() if k != field}):
        raise ValueError(f"{field} must preserve the complete ELF and every existing linker input")
    changes = {}
    for key, row in records.items():
        old = previous_records.get(key)
        if old == row:
            continue
        if old is not None:
            if field != "native_c_strings":
                raise ValueError(f"changed previously verified {field} record for {key}")
            native_strings.check_extension(old, row)
        package = Path(key).relative_to("work/analysis").parts[0]
        delta = changes.setdefault(package, Counter())
        if field == "native_c_strings":
            count = after["native_c_string_conversions"][key]
            if old is not None:
                count -= before["native_c_string_conversions"][key]
            delta["raw_pointer_type_tokens"] -= 2 * count
            delta["as_ptr_calls"] += count
        elif field == "shared_ncurses_termtypes":
            delta["raw_pointer_type_tokens"] -= after["shared_ncurses_termtype_deltas"][key]
        elif field == "shared_va_list_layouts":
            delta["raw_pointer_type_tokens"] -= after["shared_va_list_layout_deltas"][key]
        elif field == "shared_stdio_layouts":
            delta["raw_pointer_type_tokens"] -= after["shared_stdio_layout_deltas"][key]
        else:
            raise ValueError(f"unknown byte-identical source layer {field}")
    expected = Counter(before["all"])
    for delta in changes.values():
        expected.update(delta)
    if expected != after["all"] or before["packages"].keys() != after["packages"].keys():
        raise ValueError(f"{field} receipts do not explain the linked inventory")
    for package, counts in before["packages"].items():
        expected = Counter(counts)
        expected.update(changes.get(package, {}))
        if expected != after["packages"][package]:
            raise ValueError(f"unexplained {field} inventory change in {package}")


def check_shared_stdio(previous, selected, before, after):
    check_identical_layer(previous, selected, before, after, "shared_stdio_layouts")


def measure(link, inspect_source=None, *, inspect_module=None, archive_pair=None, include_standalone_modules=False):
    with tempfile.TemporaryDirectory() as temp:
        return audit(link, Path(temp), inspect_source, inspect_module=inspect_module, archive_pair=archive_pair, include_standalone_modules=include_standalone_modules)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("link_report", type=Path)
    previous = parser.add_mutually_exclusive_group()
    previous.add_argument("--verify-routing-protocols-from", type=Path, metavar="CONTROL")
    previous.add_argument("--verify-termtypes-from", type=Path, metavar="CONTROL")
    previous.add_argument("--verify-va-list-from", type=Path, metavar="CONTROL")
    previous.add_argument("--verify-native-c-strings-from", type=Path, metavar="CONTROL")
    previous.add_argument("--verify-shared-stdio-from", type=Path, metavar="CONTROL")
    previous.add_argument("--verify-lz4-dictionary-from", type=Path, metavar="CONTROL")
    previous.add_argument("--verify-bison-lengths-from", type=Path, metavar="CONTROL")
    previous.add_argument("--verify-tar-timestamps-from", type=Path, metavar="CONTROL")
    previous.add_argument("--verify-curl-manual-from", type=Path, metavar="CONTROL")
    previous.add_argument("--verify-netlink-protocols-from", type=Path, metavar="CONTROL")
    previous.add_argument("--verify-route-names-from", type=Path, metavar="CONTROL")
    previous.add_argument("--verify-address-protocols-from", type=Path, metavar="CONTROL")
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
    if args.verify_routing_protocols_from:
        prior = json.loads(args.verify_routing_protocols_from.read_bytes())
        if routing_protocols.FIELD in prior or routing_protocols.FIELD not in link:
            raise ValueError("expected a new routing protocol selection")
        check_archive_counts(prior, routing_protocols.parent_view(link), measure(prior), current,
                             link[routing_protocols.FIELD], "routing_protocol_deltas")
    if args.verify_termtypes_from:
        prior = json.loads(args.verify_termtypes_from.read_bytes())
        check_identical_layer(prior, link, measure(prior), current, "shared_ncurses_termtypes")
    if args.verify_va_list_from:
        prior = json.loads(args.verify_va_list_from.read_bytes())
        check_identical_layer(prior, link, measure(prior), current, "shared_va_list_layouts")
    if args.verify_native_c_strings_from:
        prior = json.loads(args.verify_native_c_strings_from.read_bytes())
        check_identical_layer(prior, link, measure(prior), current, "native_c_strings")
    if args.verify_shared_stdio_from:
        prior = json.loads(args.verify_shared_stdio_from.read_bytes())
        check_shared_stdio(prior, link, measure(prior), current)
    for path, layer, field in ((args.verify_lz4_dictionary_from, lz4_dictionary, "lz4_dictionary_deltas"),
                               (args.verify_bison_lengths_from, bison_lengths, "bison_length_deltas"),
                               (args.verify_tar_timestamps_from, tar_timestamps, "tar_timestamp_deltas")):
        if path:
            prior = json.loads(path.read_bytes())
            record = layer.pinned()
            if layer.field in prior or link.get(layer.field) != record:
                raise ValueError(f"missing or previously selected {layer.field} archive")
            check_archive_counts(prior, layer.parent_view(link), measure(prior), current,
                                 {layer.key: record["pilot"]}, field)
    if args.verify_curl_manual_from:
        prior = json.loads(args.verify_curl_manual_from.read_bytes())
        row = link["curl_manual"]["pilot"]
        if "curl_manual" in prior or link["curl_manual"]["selection_parent_sha256"] != prior["binary"]["sha256"]:
            raise ValueError("packed curl manual refers to another release")
        check_archive_counts(prior, curl_manual_archive.parent_view(link), measure(prior), current,
                             {row["archive"]: row}, "curl_manual_deltas")
    if args.verify_netlink_protocols_from:
        prior = json.loads(args.verify_netlink_protocols_from.read_bytes())
        rows = link["iproute2_netlink_protocols"]
        if "iproute2_netlink_protocols" in prior or any(row["control_binary_sha256"] != prior["binary"]["sha256"] for row in rows.values()):
            raise ValueError("netlink protocol archives differ from the requested transition")
        check_archive_counts(prior, route_archives.parent_view(link), measure(prior), current, rows,
                              "iproute2_netlink_protocol_deltas")
    if args.verify_route_names_from:
        prior = json.loads(args.verify_route_names_from.read_bytes())
        if "iproute2_route_names" in prior or "iproute2_route_names" not in link:
            raise ValueError("expected a new scope/realm release")
        restored = route_archives.parent_view(link)
        if any(row["control_binary_sha256"] != prior["binary"]["sha256"] for row in link["iproute2_route_names"].values()):
            raise ValueError("scope/realm substitutions refer to another parent release")
        check_archive_counts(prior, restored, measure(prior), current, link["iproute2_route_names"], "iproute2_route_name_deltas")
    if args.verify_address_protocols_from:
        previous_link = json.loads(args.verify_address_protocols_from.read_bytes())
        check_address_protocol_conversion(previous_link, link, measure(previous_link), current)
    if args.verify_dirhash_from:
        previous_link = json.loads(args.verify_dirhash_from.read_bytes())
        check_dirhash_conversion(previous_link, link, measure(previous_link), current)
    if args.link_report.read_bytes() != link_bytes:
        raise ValueError("selected link report changed during the inventory")
    print(json.dumps(current, indent=2, sort_keys=True))
