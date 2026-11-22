#!/usr/bin/env python3
"""Record strict C2Rust coverage for normalized GNU Gawk."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "work/analysis/gawk-5.4.0"
AUDIT = BASE / "translations/c2rust-0.22.1/gawk-5.4.0-normalized-audit"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    batch_manifest_path = BASE / "normalized/c2rust-compdb-batches/manifest.json"
    batch_manifest = json.loads(batch_manifest_path.read_text())
    batches = sorted(path for path in AUDIT.glob("batch-*") if path.is_dir())
    if batch_manifest["commands"] != 55 or len(batches) != 7:
        raise RuntimeError("GNU Gawk translation batch surface changed")
    modules = sorted(path for path in AUDIT.rglob("*.rs")
                     if "src" in path.relative_to(AUDIT).parts)
    maps = sorted(AUDIT.rglob("*.c_decls.json"))
    missing_maps = sorted(path.stem for path in modules
                          if not path.with_suffix(".c_decls.json").exists())
    if len(modules) != 55 or len(maps) != 53 or missing_maps != ["awkgram", "command"]:
        raise RuntimeError("GNU Gawk strict translation coverage changed")
    text = "\n".join(path.read_text(errors="replace") for path in modules)
    holes = {
        "unimplemented": len(re.findall(r"unimplemented!", text)),
        "todo": len(re.findall(r"todo!", text)),
        "panic": len(re.findall(r"panic!", text)),
    }
    if any(holes.values()):
        raise RuntimeError(f"GNU Gawk translation contains holes: {holes}")
    inventory = {
        "unsafe_tokens": len(re.findall(r"\bunsafe\b", text)),
        "mutable_raw_pointer_types": len(re.findall(r"\*mut ", text)),
        "const_raw_pointer_types": len(re.findall(r"\*const ", text)),
        "extern_c_blocks": len(re.findall(r'extern "C"', text)),
    }
    expected_inventory = {
        "unsafe_tokens": 7263,
        "mutable_raw_pointer_types": 20418,
        "const_raw_pointer_types": 20162,
        "extern_c_blocks": 7211,
    }
    if inventory != expected_inventory:
        raise RuntimeError("GNU Gawk generated pointer inventory changed")
    evidence = {
        "schema": 1,
        "release": "5.4.0",
        "recorded_at": "2026-11-22",
        "translator": {"name": "C2Rust", "version": "0.22.1",
                       "fail_on_error": True, "preserve_unused_functions": True},
        "scope": {
            "compile_actions": 55, "translated_modules": 55,
            "batches": 7, "rust_source_bytes": sum(path.stat().st_size for path in modules),
            "full_feature_oracle": True,
        },
        "result": {
            "code_translation_failures": 0,
            "holes": holes,
            "declaration_maps": len(maps),
            "declaration_map_exceptions": missing_maps,
            "exception_reason": "C2Rust source-offset assertion in Bison-generated parser metadata; code translation remains strict and complete",
        },
        "generated_inventory": inventory,
        "policy": {
            "generated_rust_repairs": 0,
            "raw_pointer_removal_deferred": True,
            "next_gate": "combine modules, compile the raw translation, and retain exact C residue only where ABI features require it",
        },
        "artifacts": {
            "batch_manifest_sha256": sha256(batch_manifest_path),
            "module_sha256": {str(path.relative_to(AUDIT)): sha256(path) for path in modules},
        },
    }
    output = ROOT / "evidence/gawk-5.4.0-translation.json"
    output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"batches": 7, "declaration_maps": 53, "holes": 0,
                      "modules": 55, "rust_source_bytes": evidence["scope"]["rust_source_bytes"]},
                     sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
