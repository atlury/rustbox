#!/usr/bin/env python3
"""Generate committed evidence for deterministic Kmod normalization."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ANALYSIS = ROOT / "work/analysis/kmod-34.3"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    manifest_path = ANALYSIS / "normalization-manifest.json"
    manifest = json.loads(manifest_path.read_text())
    normalized = ANALYSIS / "normalized"
    upstream = {}
    differentials = {}
    for compiler in ("gcc", "clang"):
        log_path = normalized / f"{compiler}-test.log"
        match = re.search(
            r"Ok:\s+(\d+).*?Expected Fail:\s+(\d+).*?Fail:\s+(\d+).*?Skipped:\s+(\d+)",
            log_path.read_text(errors="replace"), re.DOTALL,
        )
        if not match or tuple(map(int, match.groups())) != (16, 0, 0, 0):
            raise RuntimeError(f"normalized Kmod {compiler} suite is incomplete")
        upstream[compiler] = {
            "passed": 16, "expected_failures": 0, "failures": 0, "skipped": 0,
            "log_sha256": sha256(log_path),
            "testlog_sha256": sha256(normalized / f"{compiler}-testlog.json"),
        }
        differential_path = normalized / f"{compiler}-differential.json"
        differential = json.loads(differential_path.read_text())
        if differential.get("applets") != 7 or differential.get("cases") != 25 or differential.get("passed") != 25:
            raise RuntimeError(f"normalized Kmod {compiler} differential is incomplete")
        differentials[compiler] = {
            "cases": 25, "passed": 25, "sha256": sha256(differential_path),
        }

    valgrind = {}
    for name in ("kmod", "depmod", "insmod", "lsmod", "modinfo", "modprobe", "rmmod"):
        path = normalized / f"valgrind-{name}.log"
        text = path.read_text(errors="replace")
        if "ERROR SUMMARY: 0 errors" not in text or "All heap blocks were freed" not in text:
            raise RuntimeError(f"normalized Kmod {name} Valgrind result is incomplete")
        valgrind[name] = {"errors": 0, "sha256": sha256(path)}

    compiler_sources = {}
    for compiler in ("gcc", "clang"):
        database = json.loads((normalized / f"{compiler}-compile-commands.json").read_text())
        compiler_sources[compiler] = {
            str((Path(record["directory"]) / record["file"]).resolve())
            for record in database
            if (Path(record["directory"]) / record["file"]).resolve().parent.name
            in {"shared", "libkmod", "tools"}
        }
    if compiler_sources["gcc"] != compiler_sources["clang"] or len(compiler_sources["gcc"]) != 26:
        raise RuntimeError("normalized Kmod compiler closures differ")

    evidence = {
        "schema": 1,
        "recorded_at": "2026-11-24",
        "status": "deterministic C normalization at canonical parity",
        "manifest": manifest,
        "manifest_sha256": sha256(manifest_path),
        "changed_sources": ["libkmod/libkmod-file.c", "tools/kmod.c"],
        "production_sources": 26,
        "entrypoint": {
            "symbol": "rustbox_kmod_main",
            "object_binding": "GLOBAL HIDDEN",
            "standalone_wrapper": True,
        },
        "upstream_suites": upstream,
        "canonical_differentials": differentials,
        "valgrind": valgrind,
        "next_gate": "strict C2Rust translation of the exact 26-source production closure",
    }
    output = ROOT / "evidence/kmod-34.3-normalization.json"
    output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "changed_sources": 2, "production_sources": 26,
        "upstream": 32, "differential": 50, "valgrind": 7,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
