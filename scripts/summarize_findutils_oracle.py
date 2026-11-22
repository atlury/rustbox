#!/usr/bin/env python3
"""Validate and commit evidence for the signed GNU Findutils oracle."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ANALYSIS = ROOT / "work/analysis/findutils-4.10.0/oracle"
SOURCE = ROOT / "work/upstream/findutils-4.10.0"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def autotest_summaries(text: str) -> list[dict[str, int]]:
    records = []
    for match in re.finditer(
        r"# TOTAL:\s+(\d+).*?# PASS:\s+(\d+).*?# SKIP:\s+(\d+).*?"
        r"# XFAIL:\s+(\d+).*?# FAIL:\s+(\d+).*?# XPASS:\s+(\d+).*?# ERROR:\s+(\d+)",
        text, re.DOTALL,
    ):
        records.append(dict(zip(
            ("total", "pass", "skip", "xfail", "fail", "xpass", "error"),
            map(int, match.groups()),
        )))
    return records


def dejagnu(text: str) -> dict[str, dict[str, int]]:
    result = {}
    matches = list(re.finditer(r"=== (find|xargs|locate) Summary ===", text))
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        block = text[match.end():end]
        result[match.group(1)] = {
            "pass": int(re.search(r"# of expected passes\s+(\d+)", block).group(1)),
            "fail": int((re.search(r"# of unexpected failures\s+(\d+)", block) or [None, "0"])[1]),
        }
    return result


def needed(path: Path) -> list[str]:
    text = subprocess.run(
        ["readelf", "-d", str(path)], check=True, text=True,
        stdout=subprocess.PIPE,
    ).stdout
    return sorted(set(re.findall(r"Shared library: \[([^]]+)\]", text)))


def main() -> int:
    state = json.loads((ROOT / "work/upstream/.state/findutils.json").read_text())
    if not state["signature_verified"]:
        raise RuntimeError("Findutils release signature is not verified")
    differential = json.loads((ANALYSIS / "differential.json").read_text())
    if differential["cases"] != 38 or differential["passed"] != 38:
        raise RuntimeError("Findutils compiler differential is incomplete")

    expected_auto = [
        {"total": 2, "pass": 2, "skip": 0, "xfail": 0, "fail": 0, "xpass": 0, "error": 0},
        {"total": 362, "pass": 323, "skip": 39, "xfail": 0, "fail": 0, "xpass": 0, "error": 0},
        {"total": 23, "pass": 21, "skip": 2, "xfail": 0, "fail": 0, "xpass": 0, "error": 0},
    ]
    expected_dejagnu = {
        "find": {"pass": 487, "fail": 0},
        "xargs": {"pass": 96, "fail": 0},
        "locate": {"pass": 32, "fail": 0},
    }
    suites = {}
    compile_databases = {}
    installed = None
    for compiler in ("gcc", "clang", "sanitizer"):
        check_path = ANALYSIS / f"{compiler}-check.log"
        text = check_path.read_text(errors="replace")
        actual_dejagnu = dejagnu(text)
        if compiler == "sanitizer":
            expected = {**expected_dejagnu, "locate": {"pass": 31, "fail": 1}}
            if (
                text.count("FAIL: bigprefix1-1") != 1
                or len(re.findall(r"^FAIL:", text, re.MULTILINE)) != 1
            ):
                raise RuntimeError("sanitizer suite has an unexpected failure set")
        else:
            expected = expected_dejagnu
            if re.search(r"^FAIL:", text, re.MULTILINE):
                raise RuntimeError(f"{compiler} suite contains a failure")
        if actual_dejagnu != expected or autotest_summaries(text) != expected_auto:
            raise RuntimeError(f"{compiler} upstream suite summary changed")
        suites[compiler] = {
            "dejagnu": actual_dejagnu,
            "autotest": expected_auto,
            "log_sha256": sha256(check_path),
        }

        database_path = ANALYSIS / f"{compiler}-compile-commands.json"
        database = json.loads(database_path.read_text())
        sources = sorted({record["file"] for record in database})
        if len(database) != 218 or len(sources) != 218:
            raise RuntimeError(f"{compiler} compile closure changed")
        compile_databases[compiler] = {
            "commands": len(database), "sources": len(sources),
            "sha256": sha256(database_path),
        }

        installed_path = ANALYSIS / f"{compiler}-installed-files.txt"
        prefix = str(ANALYSIS / f"{compiler}-root")
        paths = [line.removeprefix(prefix) for line in installed_path.read_text().splitlines()]
        if installed is None:
            installed = paths
        elif paths != installed:
            raise RuntimeError("compiler installed-file manifests differ")

    known_log = ANALYSIS / "sanitizer-known-ub.log"
    diagnostic = "locate.c:200:32: runtime error: left shift of negative value -1"
    if known_log.read_text(errors="replace").count(diagnostic) != 1:
        raise RuntimeError("canonical Locate UB reproducer changed")

    valgrind = {}
    for name in ("find", "xargs", "locate", "frcode"):
        path = ANALYSIS / f"valgrind-{name}.log"
        text = path.read_text(errors="replace")
        if "ERROR SUMMARY: 0 errors" not in text or not (
            "All heap blocks were freed" in text
            or (
                "definitely lost: 0 bytes" in text
                and "indirectly lost: 0 bytes" in text
                and "possibly lost: 0 bytes" in text
            )
        ):
            raise RuntimeError(f"Findutils {name} Valgrind result changed")
        valgrind[name] = {"errors": 0, "log_sha256": sha256(path)}

    binaries = {}
    for name, relative in {
        "find": "usr/bin/find", "xargs": "usr/bin/xargs",
        "locate": "usr/bin/locate", "frcode": "usr/libexec/frcode",
    }.items():
        path = ANALYSIS / "gcc-root" / relative
        dependencies = needed(path)
        if any("selinux" in library or "systemd" in library for library in dependencies):
            raise RuntimeError(f"{name} retains a forbidden dependency")
        binaries[name] = {
            "bytes": path.stat().st_size, "sha256": sha256(path),
            "dynamic_needed": dependencies,
        }

    evidence = {
        "schema": 1,
        "release": "4.10.0",
        "recorded_at": "2026-11-22",
        "source": {
            **state,
            "entries": sum(1 for _ in SOURCE.rglob("*")),
        },
        "scope": {
            "public_names": ["find", "xargs", "locate", "updatedb"],
            "private_programs": ["frcode"],
            "selinux": False,
        },
        "installed_files": installed,
        "compile_databases": compile_databases,
        "upstream_suites": suites,
        "canonical_defects": [{
            "source": "locate/locate.c", "line": 200,
            "diagnostic": diagnostic,
            "trigger": "negative LOCATE02 prefix delta encoded as a signed high byte",
            "normalization_required": True,
            "log_sha256": sha256(known_log),
        }],
        "differential": differential,
        "valgrind": valgrind,
        "binaries": binaries,
    }
    output = ROOT / "evidence/findutils-4.10.0-oracle.json"
    output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "differential": differential["passed"],
        "production_sources": compile_databases["gcc"]["sources"],
        "source_entries": evidence["source"]["entries"],
        "upstream_expected_passes": sum(x["pass"] for x in expected_dejagnu.values()),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
