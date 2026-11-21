#!/usr/bin/env python3
"""Publish behavior, ownership, dependency, and size evidence for Less 710."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def section(path: Path, name: str) -> int:
    match = re.search(rf"^{re.escape(name)}\s+(\d+)\s+", path.read_text(), re.MULTILINE)
    if not match:
        raise RuntimeError(f"missing {name} in {path}")
    return int(match.group(1))


def needed(path: Path) -> list[str]:
    return re.findall(r"Shared library: \[([^]]+)\]", path.read_text())


def heap_line(path: Path) -> str:
    match = re.search(r"total heap usage:.*", path.read_text(errors="replace"))
    if not match:
        raise RuntimeError(f"missing heap summary in {path}")
    return match.group(0)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repository = args.repository.resolve()
    analysis = repository / "work/analysis/less-710/hybrid"
    build = repository / "build/less-710-hybrid"
    differential_path = analysis / "differential.json"
    differential = json.loads(differential_path.read_text())
    if differential.get("cases") != 22 or differential.get("passed") != 22:
        raise RuntimeError("Less translated differential suite is incomplete")

    valgrind = {}
    for applet in ("less", "lessecho"):
        records = {}
        for implementation in ("canonical", "hybrid"):
            path = analysis / f"valgrind-{applet}-{implementation}.log"
            text = path.read_text(errors="replace")
            if "ERROR SUMMARY: 0 errors" not in text:
                raise RuntimeError(f"Less {applet} {implementation} has Valgrind errors")
            if applet == "less":
                required = (
                    "definitely lost: 0 bytes", "indirectly lost: 0 bytes",
                    "still reachable: 5,946 bytes in 22 blocks",
                )
            else:
                required = ("All heap blocks were freed -- no leaks are possible",)
            if any(marker not in text for marker in required):
                raise RuntimeError(f"Less {applet} {implementation} ownership baseline changed")
            records[implementation] = {
                "heap_summary": heap_line(path),
                "log_sha256": sha256(path),
            }
        if records["canonical"]["heap_summary"] != records["hybrid"]["heap_summary"]:
            raise RuntimeError(f"Less {applet} translated allocation lifecycle changed")
        valgrind[applet] = records

    binary = build / "less"
    stripped = build / "less.stripped"
    canonical = build / "less.canonical-stripped"
    dynamic_path = build / "less.dynamic"
    dependencies = needed(dynamic_path)
    expected = [
        "libtinfo.so.6", "libm.so.6", "libgcc_s.so.1", "libc.so.6",
        "ld-linux-x86-64.so.2",
    ]
    if dependencies != expected:
        raise RuntimeError(f"Less translated dependencies changed: {dependencies!r}")
    sections = build / "less.sections"
    translation_path = repository / "evidence/less-710-c2rust.json"
    translation = json.loads(translation_path.read_text())
    payload = {
        "schema": 1,
        "recorded_at": "2026-11-22",
        "release": "710",
        "status": "complete translated hybrid at canonical parity; both names integrated into Rustbox",
        "implementation": {
            "production_sources": 38,
            "rust_files": translation["stable_translation"]["rust_files"],
            "public_names": ["less", "lessecho"],
            "entrypoints": ["rustbox_less_main", "rustbox_lessecho_main"],
            "generated_rust_semantic_repairs": 0,
            "type_directed_promotion_repairs": 8,
            "c_abi_glue": "argv0 dispatch only",
        },
        "behavior": {
            "differential": differential,
            "differential_sha256": sha256(differential_path),
            "valgrind": valgrind,
        },
        "size": {
            "translation_static_archive_bytes": translation["stable_translation"]["archive"]["bytes"],
            "linked_unstripped_bytes": binary.stat().st_size,
            "linked_stripped_bytes": stripped.stat().st_size,
            "canonical_stripped_bytes": canonical.stat().st_size,
            "linked_sha256": sha256(binary),
            "stripped_sha256": sha256(stripped),
            "sections": {
                name.removeprefix("."): section(sections, name)
                for name in (".text", ".rodata", ".data", ".bss")
            },
            "dynamic_needed": dependencies,
            "interpretation": "libtinfo is allowed only for this parity fixture and must be internalized before the final static release gate",
        },
        "configuration": {"selinux": False, "systemd": False},
        "input_evidence": {
            name: sha256(repository / f"evidence/{name}")
            for name in (
                "less-710-oracle.json", "less-710-analysis.json",
                "less-710-normalization.json", "less-710-c2rust.json",
            )
        },
        "next_gate": "complete; unified dispatch evidence is in evidence/rustbox-multicall.json",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "differential": differential["passed"],
        "stripped_bytes": stripped.stat().st_size,
        "valgrind_applets": len(valgrind),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
