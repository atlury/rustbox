#!/usr/bin/env python3
"""Generate evidence for defined-arithmetic GNU Findutils normalization."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NORMALIZED = ROOT / "work/analysis/findutils-4.10.0/normalized"
ORACLE = ROOT / "work/analysis/findutils-4.10.0/oracle"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def summaries(text: str) -> tuple[dict[str, dict[str, int]], list[dict[str, int]]]:
    dejagnu = {}
    matches = list(re.finditer(r"=== (find|xargs|locate) Summary ===", text))
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        block = text[match.end():end]
        dejagnu[match.group(1)] = {
            "pass": int(re.search(r"# of expected passes\s+(\d+)", block).group(1)),
            "fail": int((re.search(r"# of unexpected failures\s+(\d+)", block) or [None, "0"])[1]),
        }
    autotest = []
    for match in re.finditer(
        r"# TOTAL:\s+(\d+).*?# PASS:\s+(\d+).*?# SKIP:\s+(\d+).*?"
        r"# XFAIL:\s+(\d+).*?# FAIL:\s+(\d+).*?# XPASS:\s+(\d+).*?# ERROR:\s+(\d+)",
        text, re.DOTALL,
    ):
        autotest.append(dict(zip(
            ("total", "pass", "skip", "xfail", "fail", "xpass", "error"),
            map(int, match.groups()),
        )))
    return dejagnu, autotest


def main() -> int:
    manifest_path = ROOT / "work/analysis/findutils-4.10.0/normalization-manifest.json"
    manifest = json.loads(manifest_path.read_text())
    if manifest["changed_sources"] != ["locate/locate.c"]:
        raise RuntimeError("Findutils normalization changed an unexpected source")
    expected_dejagnu = {
        "find": {"pass": 487, "fail": 0},
        "xargs": {"pass": 96, "fail": 0},
        "locate": {"pass": 32, "fail": 0},
    }
    expected_auto = [
        {"total": 2, "pass": 2, "skip": 0, "xfail": 0, "fail": 0, "xpass": 0, "error": 0},
        {"total": 362, "pass": 323, "skip": 39, "xfail": 0, "fail": 0, "xpass": 0, "error": 0},
        {"total": 23, "pass": 21, "skip": 2, "xfail": 0, "fail": 0, "xpass": 0, "error": 0},
    ]
    compilers = {}
    source_count = None
    for compiler in ("gcc", "clang", "sanitizer"):
        check_path = NORMALIZED / f"{compiler}-check.log"
        text = check_path.read_text(errors="replace")
        dejagnu, autotest = summaries(text)
        if (
            dejagnu != expected_dejagnu
            or autotest != expected_auto
            or re.search(r"^FAIL:", text, re.MULTILINE)
            or "runtime error:" in text
            or "ERROR: AddressSanitizer" in text
        ):
            raise RuntimeError(f"normalized {compiler} suite changed")
        database_path = NORMALIZED / f"{compiler}-compile-commands.json"
        database = json.loads(database_path.read_text())
        sources = {record["file"] for record in database}
        if len(database) != 218 or len(sources) != 218:
            raise RuntimeError(f"normalized {compiler} compile closure changed")
        source_count = len(sources) if source_count is None else source_count
        compilers[compiler] = {
            "compile_actions": len(database),
            "production_sources": len(sources),
            "compile_database_sha256": sha256(database_path),
            "dejagnu": dejagnu,
            "autotest": autotest,
            "check_log_sha256": sha256(check_path),
        }

        canonical_manifest = ORACLE / f"{compiler}-installed-files.txt"
        normalized_manifest = NORMALIZED / f"{compiler}-installed-files.txt"
        canonical_prefix = str(ORACLE / f"{compiler}-root")
        normalized_prefix = str(NORMALIZED / f"{compiler}-root")
        canonical_paths = [line.removeprefix(canonical_prefix)
                           for line in canonical_manifest.read_text().splitlines()]
        normalized_paths = [line.removeprefix(normalized_prefix)
                            for line in normalized_manifest.read_text().splitlines()]
        if canonical_paths != normalized_paths:
            raise RuntimeError(f"normalized {compiler} installed surface changed")

    differentials = {}
    for compiler in ("gcc", "clang"):
        path = NORMALIZED / f"{compiler}-differential.json"
        result = json.loads(path.read_text())
        if result["cases"] != 38 or result["passed"] != 38:
            raise RuntimeError(f"normalized {compiler} differential changed")
        differentials[compiler] = {
            "cases": 38, "passed": 38, "sha256": sha256(path),
        }

    valgrind = {}
    for name in ("find", "xargs", "locate", "frcode"):
        path = NORMALIZED / f"valgrind-{name}.log"
        text = path.read_text(errors="replace")
        if "ERROR SUMMARY: 0 errors" not in text or not (
            "All heap blocks were freed" in text
            or (
                "definitely lost: 0 bytes" in text
                and "indirectly lost: 0 bytes" in text
                and "possibly lost: 0 bytes" in text
            )
        ):
            raise RuntimeError(f"normalized {name} Valgrind result changed")
        valgrind[name] = {"errors": 0, "log_sha256": sha256(path)}

    evidence = {
        "schema": 1,
        "release": "4.10.0",
        "recorded_at": "2026-11-22",
        "status": "complete deterministic defined-arithmetic normalization",
        "manifest": manifest,
        "manifest_sha256": sha256(manifest_path),
        "scope": {
            "production_sources": source_count,
            "changed_sources": ["locate/locate.c"],
            "public_names": ["find", "xargs", "locate", "updatedb"],
        },
        "compilers": compilers,
        "behavior": {
            "canonical_differentials": differentials,
            "sanitizer": {
                "address_errors": 0,
                "undefined_behavior_diagnostics": 0,
                "canonical_signed_shift_removed": True,
            },
            "valgrind": valgrind,
        },
        "next_gate": "export multicall entrypoints and probe the exact production closure with C2Rust",
    }
    output = ROOT / "evidence/findutils-4.10.0-normalization.json"
    output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "changed_sources": 1, "differential": 76,
        "production_sources": source_count, "ubsan": 0, "valgrind": 4,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
