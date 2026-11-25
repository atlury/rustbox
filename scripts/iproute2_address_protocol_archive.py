"""Select and replay the compiler-verified IPRoute2 address-protocol archive."""
# SPDX-License-Identifier: GPL-2.0-or-later
from concurrent.futures import ThreadPoolExecutor
import json
import re
import shutil
from pathlib import Path
import tempfile

from build_iproute2_bridge_address_protocols import BRIDGE, build_bridge_trial, compile_bridge
from check_cargo_private_inlines import IPROUTE2_CARGO_ENGINES, ROOT, digest
from check_e2fsprogs_dirhash_arrays import source_list_digest
from stage_iproute2_address_protocols import BRIDGE_MODULE_SHA256, MODULE, compiler_inputs, replace_table

ARCHIVE = Path("work/analysis/iproute2-7.3.0/program-translations/cargo-target/ip/release/libip_audit.a")
COPIES = Path("batches/iproute2-address-protocol-copies.json")
MANIFEST = Path("batches/iproute2-address-protocols.json")
RECEIPTS = ("linked_private_inline_proofs", "linked_second_inline_proofs", "linked_foreign_declaration_proofs")


def candidate_path(record):
    archive = Path(record["archive"])
    engine = archive.parent.parent.name
    expected = ARCHIVE.parents[2] / engine / "release" / f"lib{engine}_audit.a"
    if ((archive != BRIDGE and (engine not in IPROUTE2_CARGO_ENGINES or archive != expected))
            or not re.fullmatch(r"[0-9a-f]{64}", record["candidate_sha256"])):
        raise ValueError("invalid address-protocol archive path or checksum")
    base = archive.parent if archive == BRIDGE else archive.parent.parent
    return base / "address-protocols" / record["candidate_sha256"] / archive.name


def pinned(repository=ROOT):
    record = json.loads((repository / MANIFEST).read_bytes())
    if record["archive"] != str(ARCHIVE) or set(record["parent_receipts"]) != set(RECEIPTS):
        raise ValueError("unexpected address-protocol archive manifest")
    return record


def pinned_copies(repository=ROOT):
    records = json.loads((repository / COPIES).read_bytes())
    pilot = pinned(repository)
    expected = {str(ARCHIVE.parents[2] / engine / "release" / f"lib{engine}_audit.a")
                for engine in IPROUTE2_CARGO_ENGINES if engine != "ip"}
    expected.add(str(BRIDGE))
    if records.keys() != expected:
        raise ValueError("expected all 17 remaining address-protocol copies")
    for key, record in records.items():
        bridge = Path(key) == BRIDGE
        if (record["archive"] != key or record["raw_pointer_types_removed_in_pilot_module"] != pilot["raw_pointer_types_removed_in_pilot_module"]
                or record["control_module_sha256"] != (BRIDGE_MODULE_SHA256 if bridge else pilot["control_module_sha256"])
                or (not bridge and record["candidate_module_sha256"] != pilot["candidate_module_sha256"])):
            raise ValueError(f"unexpected compiler-selected address-protocol module for {key}")
        candidate_path(record)
    return records


def validate_control(link, record):
    key = record["archive"]
    if (link["source_library_sha256"].get(key) != record["control_sha256"]
            or {k: link[k][key] for k in RECEIPTS if key in link.get(k, {})} != record["parent_receipts"]):
        raise ValueError("IPRoute2 address-protocol parent archive or source receipts differ")


def selected_records(link):
    record = link.get("iproute2_address_protocols")
    copies = link.get("iproute2_address_protocol_copies")
    if record is None:
        if copies is not None:
            raise ValueError("address-protocol copies have no qualified ip parent")
        return {}
    if record != pinned() or (copies is not None and copies != pinned_copies()):
        raise ValueError("unexpected IPRoute2 address-protocol selection")
    return {record["archive"]: record, **(copies or {})}


def control_view(link):
    if "iproute2_route_names" in link:
        from iproute2_route_name_archives import parent_view
        link = parent_view(link)
    records = selected_records(link)
    if not records:
        return link
    hashes = link["source_library_sha256"].copy()
    for key, record in records.items():
        if key in hashes or hashes.pop(str(candidate_path(record)), None) != record["candidate_sha256"]:
            raise ValueError("address-protocol candidate is missing or ambiguous")
        hashes[key] = record["control_sha256"]
    control = dict(link, source_library_sha256=hashes)
    del control["iproute2_address_protocols"]
    control.pop("iproute2_address_protocol_copies", None)
    for record in records.values():
        validate_control(control, record)
    return control


def build_control_view(link):
    """Rebuild historical controls even when the current link already selects the candidates."""
    control = control_view(link)
    if record := link.get("iproute2_address_protocols"):
        return dict(control, binary={"sha256": record["control_binary_sha256"]})
    return control


def verify_sources(record, sources, changes):
    if (len(sources) != record["compiler_selected_sources"] or any(record[k] != v for k, v in changes.items())
            or sources[str(MODULE)] != record["control_module_sha256"]
            or source_list_digest(sources) != record["parent_sources_sha256"]
            or source_list_digest({**sources, str(MODULE): changes["candidate_module_sha256"]}) != record["candidate_sources_sha256"]):
        raise ValueError("IPRoute2 compiler inputs differ from the pinned address-protocol substitution")


def prepare_record(record, verified_archive=None):
    from build_iproute2_address_protocol_pilot import build_pilot

    key = record["archive"]
    control = {"binary": {"sha256": record["control_binary_sha256"]},
               "source_library_sha256": {key: record["control_sha256"]},
               **{k: {key: v} for k, v in record["parent_receipts"].items()}}
    original, files = compiler_inputs(control, key)
    _, changes = replace_table(original)
    verify_sources(record, {str(k): v for k, v in files.items()}, changes)
    target = ROOT / candidate_path(record)
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=target.parent) as scratch:
            output = Path(scratch) / "candidate"
            if verified_archive is None:
                if Path(key) == BRIDGE:
                    build_bridge_trial(output, control)
                else:
                    build_pilot(output, control, Path(key).parent.parent.name)
                archive = output / Path(key).name
            else:
                archive = Path(scratch) / Path(key).name
                shutil.copyfile(verified_archive, archive)
            if digest(archive) != record["candidate_sha256"]:
                raise ValueError("fresh Cargo candidate differs from qualified archive")
            archive.replace(target)
    if digest(target) != record["candidate_sha256"]:
        raise ValueError("cached address-protocol archive differs from manifest")
    print(f"Verified address-protocol archive {record['candidate_sha256']}")


def prepare(include_copies=False):
    prepare_record(pinned())
    if include_copies:
        with ThreadPoolExecutor(max_workers=3) as pool:
            list(pool.map(prepare_record, (r for k, r in pinned_copies().items() if Path(k) != BRIDGE)))


def prepare_bridge_for_link(control, record, repository):
    """The custom bridge parent is built inside the Linux linker, before this stage."""
    target = repository / candidate_path(record)
    validate_control(control, record)
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=target.parent) as tmp:
            output = Path(tmp)
            result = compile_bridge(dict(control, binary={"sha256": record["control_binary_sha256"]}), output)
            if dict(result, parent_receipts=record["parent_receipts"]) != record:
                raise ValueError("fresh bridge archive differs from its pinned compiler evidence")
            (output / BRIDGE.name).replace(target)
    if digest(target) != record["candidate_sha256"]:
        raise ValueError("cached bridge address-protocol archive differs from manifest")


def comparison_inputs():
    paths = ("work/upstream/iproute2-7.3.0/lib/rt_names.c", "work/upstream/iproute2-7.3.0/include/rt_names.h",
             "work/analysis/iproute2-7.3.0/oracle/gcc-compile-commands.json", "tests/iproute2-address-protocols/compare.c",
             "tests/iproute2-address-protocols/archives.py", "tests/iproute2-address-protocols/configuration.py",
             "scripts/test_iproute2_address_protocols.sh")
    inputs = {name: digest(ROOT / name) for name in paths}
    headers = ROOT / "work/upstream/iproute2-7.3.0/include"
    inputs["iproute2_include_headers"] = source_list_digest({str(p.relative_to(headers)): digest(p) for p in headers.rglob("*.h")})
    return inputs


def validate_copy_results(records, result, pilot_checks, image_id):
    checks = result["lookup_checks"]
    engines = [Path(k).stem.removeprefix("lib").removesuffix("_audit") for k in records]
    variants = {f"{engine}-{suffix}" for engine in engines for suffix in ("parent", "candidate", "candidate-memcheck")}
    if (result["archive_sha256"] != {k: r["candidate_sha256"] for k, r in records.items()}
            or result["control_sha256"] != {k: r["control_sha256"] for k, r in records.items()}
            or result["test_input_sha256"] != comparison_inputs() or result["image_id"] != image_id
            or len(checks["variants_compared_to_canonical"]) != len(variants) or set(checks["variants_compared_to_canonical"]) != variants
            or any(checks[key] != pilot_checks[key] for key in ("configurations", "lookup_results_per_variant", "deferred_load_and_cache_checks_per_variant"))
            or checks["memcheck_runs"] != len(records) * pilot_checks["memcheck_runs"]):
        raise ValueError("canonical lookup results do not cover the exact release archive set and test inputs")
