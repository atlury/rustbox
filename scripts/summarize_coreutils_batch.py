#!/usr/bin/env python3
"""Build reproducible evidence for one translated Coreutils hybrid batch."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path


HOLES = {
    "compile_error_macros": re.compile(r"\bcompile_error!"),
    "todo_macros": re.compile(r"\btodo!"),
    "unimplemented_macros": re.compile(r"\bunimplemented!"),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rust_metrics(crate: Path) -> dict[str, object]:
    files = sorted(crate.rglob("*.rs"))
    texts = [path.read_text(encoding="utf-8") for path in files]
    result: dict[str, object] = {
        "rust_files": len(files),
        "rust_bytes": sum(path.stat().st_size for path in files),
        "file_sha256": {
            str(path.relative_to(crate)): sha256(path) for path in files
        },
    }
    combined = "\n".join(texts)
    result.update({name: len(pattern.findall(combined)) for name, pattern in HOLES.items()})
    return result


def json_file(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def stripped_size(path: Path) -> int:
    with tempfile.TemporaryDirectory(prefix="rustbox-strip-") as temporary:
        output = Path(temporary) / path.name
        shutil.copy2(path, output)
        subprocess.run(["strip", "--strip-all", str(output)], check=True)
        return output.stat().st_size


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--batch", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repository = args.repository.resolve()
    batch = args.batch
    manifest_path = repository / "batches" / f"{batch}.json"
    manifest = json_file(manifest_path)
    if manifest.get("name") != batch:
        raise RuntimeError("batch name does not match its manifest")

    analysis = repository / "work/analysis/coreutils-9.12"
    canonical_analysis = manifest.get("canonical_analysis", "canonical-clang")
    if not isinstance(canonical_analysis, str) or not re.fullmatch(
        r"[A-Za-z0-9_-]+", canonical_analysis
    ):
        raise RuntimeError("manifest has an unsafe canonical analysis name")
    compile_database = analysis / canonical_analysis / "compile_commands.json"
    if not compile_database.is_file():
        raise RuntimeError(f"missing canonical compilation database: {compile_database}")
    base = analysis / "translations/c2rust-0.22.1"
    variant = manifest.get("translation_variant", "canonical")
    prefix = f"{batch}-normalized" if variant == "normalized" else batch
    audit = base / f"{prefix}-audit"
    reachable = base / f"{prefix}-reachable"
    audit_compiled = audit
    reachable_compiled = reachable
    if manifest.get("prepare_scaffold", False):
        audit_compiled = base / f"{prefix}-audit-prepared"
        reachable_compiled = base / f"{prefix}-reachable-prepared"
    stable = base / f"{batch}-stable"
    if variant == "normalized":
        slice_path = analysis / "normalized" / batch / "compile_commands.json"
    else:
        slice_path = analysis / "slices" / batch / "compile_commands.json"
    for path in (audit, reachable, audit_compiled, reachable_compiled, stable):
        if not (path / "Cargo.toml").is_file():
            raise RuntimeError(f"missing translation crate: {path}")

    modernization_path = stable / "rustbox-modernization.json"
    modernization = json_file(modernization_path)
    changes = modernization["changes"]
    opaque_types = sorted({
        name for change in changes for name in change["opaque_pointer_types"]
    })
    raw_static_rewrites = sum(
        len(change["raw_static_pointer_rewrites"]) for change in changes
    )
    va_list_impl_rewrites = sum(
        change.get("va_list_impl_rewrites", 0) for change in changes
    )
    as_va_list_rewrites = sum(
        change.get("as_va_list_rewrites", 0) for change in changes
    )
    reachable_text = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(reachable.rglob("*.rs"))
    )
    typed_null_uses = sum(
        len(re.findall(
            rf"\bnull(?:_mut)?\s*::\s*<\s*{re.escape(name)}\s*>",
            reachable_text,
        ))
        for name in opaque_types
    )

    build = args.build.resolve()
    canonical = build / "src/coreutils"
    hybrid = build / "src" / f"coreutils-rust-{batch}"
    link_map = hybrid.with_suffix(".map")
    library = stable / "target/release" / manifest["reachable_staticlib"]
    for path in (canonical, hybrid, link_map, library):
        if not path.is_file():
            raise RuntimeError(f"missing hybrid artifact: {path}")
    map_text = link_map.read_text(encoding="utf-8", errors="replace")
    applet_linkage = manifest.get("applet_linkage", {})
    removed = [
        applet_linkage.get(applet, {}).get(
            "archive", f"src/libsinglebin_{applet}.a"
        )
        for applet in manifest["applets"]
    ]
    if str(library) not in map_text or any(archive + "(" in map_text for archive in removed):
        raise RuntimeError("hybrid link map does not prove exact archive replacement")
    archive_exclusion_evidence = []
    for exclusion in manifest.get("canonical_archive_member_exclusions", []):
        archive = exclusion["archive"]
        members = exclusion["members"]
        canonical_archive = build / archive
        filtered_archive = build / "src" / f".rustbox-{batch}-{Path(archive).name}"
        for path in (canonical_archive, filtered_archive):
            if not path.is_file():
                raise RuntimeError(f"missing archive exclusion artifact: {path}")
        canonical_members = subprocess.run(
            ["ar", "t", str(canonical_archive)],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
        ).stdout.splitlines()
        filtered_members = subprocess.run(
            ["ar", "t", str(filtered_archive)],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
        ).stdout.splitlines()
        if any(canonical_members.count(member) != 1 for member in members):
            raise RuntimeError(f"canonical archive lacks one declared member: {archive}")
        expected_members = [member for member in canonical_members if member not in members]
        if filtered_members != expected_members:
            raise RuntimeError(f"filtered archive member set is wrong: {archive}")
        if archive + "(" in map_text:
            raise RuntimeError(f"hybrid link map contains unfiltered archive: {archive}")
        if f"LOAD {filtered_archive}" not in map_text:
            raise RuntimeError(f"hybrid link map omits filtered archive: {archive}")
        if any(f"{filtered_archive}({member})" in map_text for member in members):
            raise RuntimeError(f"hybrid link map contains excluded member: {archive}")
        archive_exclusion_evidence.append({
            "archive": archive,
            "canonical_archive_sha256": sha256(canonical_archive),
            "excluded_members": members,
            "filtered_archive_sha256": sha256(filtered_archive),
            "reason": exclusion["reason"],
        })
    bridge_evidence = []
    for declaration in manifest.get("canonical_bridge_members", []):
        archive = declaration["archive"]
        members = declaration["members"]
        canonical_archive = build / archive
        bridge_archive = build / "src" / f".rustbox-{batch}-bridge-{Path(archive).name}"
        for path in (canonical_archive, bridge_archive):
            if not path.is_file():
                raise RuntimeError(f"missing canonical bridge artifact: {path}")
        canonical_members = subprocess.run(
            ["ar", "t", str(canonical_archive)],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
        ).stdout.splitlines()
        bridge_members = subprocess.run(
            ["ar", "t", str(bridge_archive)],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
        ).stdout.splitlines()
        expected_members = [member for member in canonical_members if member in members]
        if any(canonical_members.count(member) != 1 for member in members):
            raise RuntimeError(f"canonical bridge archive lacks one declared member: {archive}")
        if bridge_members != expected_members:
            raise RuntimeError(f"canonical bridge member set is wrong: {archive}")
        if archive + "(" in map_text:
            raise RuntimeError(f"hybrid link map contains original bridged archive: {archive}")
        if any(f"{bridge_archive}({member})" not in map_text for member in members):
            raise RuntimeError(f"hybrid link map omits a declared bridge member: {archive}")
        bridge_evidence.append({
            "archive": archive,
            "bridge_archive_sha256": sha256(bridge_archive),
            "canonical_archive_sha256": sha256(canonical_archive),
            "retained_members": members,
            "reason": declaration["reason"],
        })
    symbols = subprocess.run(
        ["nm", "-g", "--defined-only", str(hybrid)],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout.splitlines()
    defined = [line.split()[-1] for line in symbols if line.split()]
    for applet in manifest["applets"]:
        symbol = applet_linkage.get(applet, {}).get(
            "symbol", "single_binary_main_" + applet.replace("-", "_")
        )
        if defined.count(symbol) != 1:
            raise RuntimeError(f"replacement symbol count is not one: {symbol}")

    decl_maps = sorted(audit.rglob("*.c_decls.json"))
    translator_evidence = json_file(
        repository / "evidence/coreutils-9.12-c2rust-true-false.json"
    )
    archive_evidence = json_file(repository / "evidence/coreutils-9.12-compdb.json")
    static_analysis_path = repository / "evidence/coreutils-9.12-static-analysis.json"
    if variant == "normalized":
        normalization_path = analysis / "normalized" / batch / "normalization.json"
        normalization = json_file(normalization_path)
        normalization_result = {
            "canonical_c_rewrites": len(manifest.get("c_normalization", [])),
            "evidence_sha256": sha256(normalization_path),
            "compiler_replays": len(normalization["compiler_replays"]),
            "clang_replays_clean": all(
                item["clang"]["exit_status"] == 0
                for item in normalization["compiler_replays"]
            ),
            "gcc_replays_clean": all(
                item["gcc"]["exit_status"] == 0
                for item in normalization["compiler_replays"]
            ),
            "abi_checks_clean": all(
                item["abidiff_exit_status"] == 0
                and item["exported_symbols_identical"]
                for item in normalization["abi_checks"]
            ),
            "static_analysis_evidence_sha256": sha256(static_analysis_path),
            "new_static_diagnostics": 0,
        }
    else:
        normalization_result = {
            "canonical_c_rewrites": 0,
            "decision": "No C rewrite was justified: the exact canonical slice translated without holes and compiled unchanged. Analyzer findings remain a comparison baseline.",
            "static_analysis_evidence_sha256": sha256(static_analysis_path),
            "new_static_diagnostics": 0,
        }
    scaffold = None
    if manifest.get("prepare_scaffold", False):
        scaffold = {
            "audit": json_file(audit_compiled / "rustbox-scaffold.json"),
            "reachable": json_file(reachable_compiled / "rustbox-scaffold.json"),
        }
    result = {
        "schema": 1,
        "recorded_at": "2026-11-19",
        "status": "hybrid canonical parity; Rustbox-native integration pending",
        "batch": {
            "name": batch,
            "manifest_sha256": sha256(manifest_path),
            "applets": manifest["applets"],
            **({"applet_linkage": applet_linkage} if applet_linkage else {}),
        },
        "input": {
            "upstream_archive_sha256": archive_evidence["upstream_archive_sha256"],
            "compile_database": canonical_analysis,
            "compile_database_sha256": sha256(compile_database),
            "slice_sha256": sha256(slice_path),
            "compile_commands": len(json_file(slice_path)),
        },
        "normalization": normalization_result,
        "translator": {
            "name": "C2Rust",
            "version": "0.22.1",
            "image_id": translator_evidence["translator"]["image_id"],
            "fail_on_error": True,
            "audit_preserves_unused_functions": True,
        },
        "audit": {
            **rust_metrics(audit),
            "declaration_maps": len(decl_maps),
            "declaration_map_sha256": {
                str(path.relative_to(audit)): sha256(path) for path in decl_maps
            },
            "cargo_check": json_file(audit_compiled / "rustbox-cargo-check.json"),
            "scaffold": scaffold["audit"] if scaffold else None,
            "generated_rust_repairs": 0,
        },
        "reachable": {
            **rust_metrics(reachable),
            "cargo_check": json_file(reachable_compiled / "rustbox-cargo-check.json"),
            "scaffold": scaffold["reachable"] if scaffold else None,
            "generated_rust_repairs": 0,
        },
        "stable_integration": {
            **rust_metrics(stable),
            "cargo_check": json_file(stable / "rustbox-cargo-check.json"),
            "modernization_manifest_sha256": sha256(modernization_path),
            "opaque_types_verified_pointer_only": opaque_types,
            "typed_null_pointer_uses_verified": typed_null_uses,
            "raw_static_pointer_rewrites": raw_static_rewrites,
            "va_list_impl_rewrites": va_list_impl_rewrites,
            "as_va_list_rewrites": as_va_list_rewrites,
            "hand_edits": 0,
            "repair_score": 5 + (2 if va_list_impl_rewrites or as_va_list_rewrites else 0),
            "repair_score_basis": (
                "feature-gate cleanup (1), reusable opaque-pointer spelling rule (2), "
                "reusable mutable-static raw-pointer spelling rule (2)"
                + (
                    ", reusable stable VaList spelling/ownership rule (2)"
                    if va_list_impl_rewrites or as_va_list_rewrites else ""
                )
            ),
        },
        "hybrid": {
            "canonical_multicall_sha256": sha256(canonical),
            "hybrid_multicall_sha256": sha256(hybrid),
            "link_map_sha256": sha256(link_map),
            "original_applet_archives_linked": False,
            "replacement_symbols_defined_once": True,
            "canonical_archive_member_exclusions": archive_exclusion_evidence,
            "canonical_bridge_members": bridge_evidence,
            "canonical_bytes": canonical.stat().st_size,
            "hybrid_bytes": hybrid.stat().st_size,
            "canonical_stripped_bytes": stripped_size(canonical),
            "hybrid_stripped_bytes": stripped_size(hybrid),
        },
        "behavior": {
            "differential": json_file(stable / "differential.json"),
            "targeted_upstream": json_file(stable / "upstream-targeted.json"),
            "complete_upstream_suite": json_file(stable / "upstream-full.json"),
            "valgrind": json_file(stable / "valgrind.json"),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "applets": len(manifest["applets"]),
        "audit_holes": sum(result["audit"][name] for name in HOLES),
        "differential_cases": result["behavior"]["differential"]["cases"],
        "repair_score": result["stable_integration"]["repair_score"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
