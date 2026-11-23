#!/usr/bin/env python3
"""Generate evidence for deterministic GNU Inetutils normalization."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ANALYSIS = ROOT / "work/analysis/inetutils-2.8"
NORMALIZED = ROOT / "work/normalized/inetutils-2.8"
BUILD_ROOT = Path("/rustbox-inetutils")
EXECUTABLES = {
    "dnsdomainname": "src/dnsdomainname", "ftp": "ftp/ftp",
    "ftpd": "ftpd/ftpd", "hostname": "src/hostname",
    "ifconfig": "ifconfig/ifconfig", "inetd": "src/inetd",
    "logger": "src/logger", "ping": "ping/ping", "ping6": "ping/ping6",
    "rcp": "src/rcp", "rexec": "src/rexec", "rexecd": "src/rexecd",
    "rlogin": "src/rlogin", "rlogind": "src/rlogind",
    "rsh": "src/rsh", "rshd": "src/rshd", "syslogd": "src/syslogd",
    "talk": "talk/talk", "talkd": "talkd/talkd",
    "telnet": "telnet/telnet", "telnetd": "telnetd/telnetd",
    "tftp": "src/tftp", "tftpd": "src/tftpd",
    "traceroute": "src/traceroute", "uucpd": "src/uucpd",
    "whois": "whois/whois",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def closure(path: Path) -> tuple[list[str], int]:
    records = json.loads(path.read_text())
    prefix = "/rustbox-inetutils/normalized-source/"
    sources = {
        str(record["file"]).removeprefix(prefix)
        for record in records
        if str(record["file"]).startswith(prefix)
    }
    if len(sources) != len(records):
        raise RuntimeError("normalized Inetutils compile database escapes staged source")
    return sorted(sources), len(records)


def suite(path: Path) -> dict[str, int]:
    text = path.read_text(errors="replace")
    result = {
        key.lower(): int(match.group(1))
        for key in ("TOTAL", "PASS", "SKIP", "XFAIL", "FAIL", "XPASS", "ERROR")
        if (match := re.search(rf"^# {key}:\s+(\d+)$", text, re.MULTILINE))
    }
    expected = {"total": 17, "pass": 11, "skip": 5, "xfail": 0,
                "fail": 1, "xpass": 0, "error": 0}
    if result != expected or "sethostname: Operation not permitted" not in text:
        raise RuntimeError("normalized Inetutils upstream result changed")
    return result


def main() -> int:
    manifest_path = ANALYSIS / "normalization-manifest.json"
    manifest = json.loads(manifest_path.read_text())
    if (
        len(manifest.get("changed_sources", [])) != 27
        or len(manifest.get("entrypoints", {})) != 26
        or manifest.get("conditional") != "RUSTBOX_MULTICALL"
    ):
        raise RuntimeError("Inetutils normalization manifest is incomplete")

    normalized = ANALYSIS / "normalized"
    closures = {}
    actions = {}
    suites = {}
    differentials = {}
    for compiler in ("gcc", "clang"):
        database = normalized / f"{compiler}-compile-commands.json"
        closures[compiler], actions[compiler] = closure(database)
        suites[compiler] = suite(normalized / f"{compiler}-test-suite.log")
        if (normalized / f"{compiler}-test.status").read_text().strip() != "2":
            raise RuntimeError(f"normalized Inetutils {compiler} status changed")
        differential = json.loads((normalized / f"{compiler}-differential.json").read_text())
        if differential.get("cases") != 52 or differential.get("passed") != 52:
            raise RuntimeError(f"normalized Inetutils {compiler} differential changed")
        differentials[compiler] = differential
    if closures["gcc"] != closures["clang"] or actions != {"gcc": 288, "clang": 288}:
        raise RuntimeError("normalized Inetutils compiler closures differ")

    exports = {}
    for compiler in ("gcc", "clang"):
        build = BUILD_ROOT / f"normalized-{compiler}"
        exports[compiler] = {}
        for name, relative in EXECUTABLES.items():
            binary = build / relative
            output = subprocess.run(
                ["nm", "-g", "--defined-only", str(binary)], check=True,
                text=True, stdout=subprocess.PIPE,
            ).stdout
            symbol = f"rustbox_inetutils_{name}_main"
            count = len(re.findall(rf"\b{re.escape(symbol)}$", output, re.MULTILINE))
            if count != 1:
                raise RuntimeError(f"{compiler} {name} entrypoint count is {count}")
            exports[compiler][name] = symbol

    valgrind = {}
    for name in ("hostname", "dnsdomainname", "ifconfig", "whois"):
        path = normalized / f"valgrind-{name}.log"
        text = path.read_text(errors="replace")
        if "ERROR SUMMARY: 0 errors" not in text:
            raise RuntimeError(f"normalized Inetutils {name} Valgrind changed")
        valgrind[name] = {"errors": 0, "log_sha256": sha256(path)}

    evidence = {
        "schema": 1,
        "recorded_at": "2026-11-23",
        "release": "2.8",
        "canonical_archive_sha256": manifest["canonical_archive_sha256"],
        "trees": {
            "canonical_sha256": manifest["canonical_tree_sha256"],
            "normalized_sha256": manifest["normalized_tree_sha256"],
        },
        "normalization": {
            "engine": manifest["engine"],
            "changed_sources": manifest["changed_sources"],
            "entrypoints": manifest["entrypoints"],
            "conditional": manifest["conditional"],
            "transformations": manifest["transformations"],
            "file_set_preserved": True,
        },
        "build": {
            "compile_actions": actions,
            "unique_production_sources": len(closures["gcc"]),
            "production_sources": closures["gcc"],
            "exports": exports,
        },
        "tests": {
            "gcc_upstream": suites["gcc"],
            "clang_upstream": suites["clang"],
            "environmental_hostname_failure_preserved": True,
            "differential": {
                compiler: {"cases": value["cases"], "passed": value["passed"]}
                for compiler, value in differentials.items()
            },
            "valgrind": valgrind,
        },
        "next_gate": "no-hole C2Rust translation of the exact 288-source normalized closure",
        "artifacts": {
            "manifest_sha256": sha256(manifest_path),
            **{
                path.name: sha256(path)
                for path in normalized.iterdir() if path.is_file()
            },
        },
    }
    output = ROOT / "evidence/inetutils-2.8-normalization.json"
    output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "changed_sources": 27, "entrypoints": 26,
        "differential_cases": 104, "production_sources": len(closures["gcc"]),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
