#!/usr/bin/env python3
"""Generate committed evidence for the canonical GNU Inetutils 2.8 oracle."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ORACLE = ROOT / "work/analysis/inetutils-2.8/oracle"
SOURCE = ROOT / "work/upstream/inetutils-2.8"
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


def source_closure(database: Path) -> tuple[list[str], int]:
    records = json.loads(database.read_text(encoding="utf-8"))
    prefix = "/work/work/upstream/inetutils-2.8/"
    sources = {
        str(record["file"]).removeprefix(prefix)
        for record in records
        if str(record["file"]).startswith(prefix)
    }
    if len(sources) != len(records):
        raise RuntimeError("Inetutils compile database escapes signed source root")
    return sorted(sources), len(records)


def suite_summary(path: Path) -> dict[str, int]:
    text = path.read_text(errors="replace")
    summary = {
        key.lower(): int(match.group(1))
        for key in ("TOTAL", "PASS", "SKIP", "XFAIL", "FAIL", "XPASS", "ERROR")
        if (match := re.search(rf"^# {key}:\s+(\d+)$", text, re.MULTILINE))
    }
    expected = {
        "total": 17, "pass": 11, "skip": 5, "xfail": 0,
        "fail": 1, "xpass": 0, "error": 0,
    }
    if summary != expected:
        raise RuntimeError(f"Inetutils suite totals changed: {summary}")
    if (
        len(re.findall(r"^FAIL: hostname\.sh$", text, re.MULTILINE)) != 1
        or "sethostname: Operation not permitted" not in text
    ):
        raise RuntimeError("Inetutils environmental hostname failure changed")
    return summary


def main() -> int:
    release = json.loads((ROOT / "upstream/releases.json").read_text())["releases"]["inetutils"]
    state = json.loads((ROOT / "work/upstream/.state/inetutils.json").read_text())
    for key in ("version", "sha256", "signature_sha256", "signer_fingerprint", "key_sha256"):
        if state.get(key) != release[key]:
            raise RuntimeError(f"Inetutils source state changed at {key}")
    if state.get("signature_verified") is not True:
        raise RuntimeError("Inetutils release signature is not verified")

    artifacts = {
        name: ORACLE / name for name in (
            "gcc-build.log", "clang-build.log",
            "gcc-compile-commands.json", "clang-compile-commands.json",
            "gcc-test.log", "clang-test.log", "gcc-test.status",
            "clang-test.status", "gcc-test-suite.log", "clang-test-suite.log",
            "differential.json", "valgrind-hostname.log",
            "valgrind-dnsdomainname.log", "valgrind-ifconfig.log",
            "valgrind-whois.log",
        )
    }
    for path in artifacts.values():
        if not path.is_file():
            raise RuntimeError(f"missing Inetutils oracle artifact: {path}")

    closures = {}
    actions = {}
    suites = {}
    for compiler in ("gcc", "clang"):
        closures[compiler], actions[compiler] = source_closure(
            artifacts[f"{compiler}-compile-commands.json"]
        )
        suites[compiler] = suite_summary(artifacts[f"{compiler}-test-suite.log"])
        if artifacts[f"{compiler}-test.status"].read_text().strip() != "2":
            raise RuntimeError(f"Inetutils {compiler} suite status changed")
    if closures["gcc"] != closures["clang"] or actions != {"gcc": 288, "clang": 288}:
        raise RuntimeError("Inetutils compiler production closures differ")

    differential = json.loads(artifacts["differential.json"].read_text())
    if (
        differential.get("applets") != 26
        or differential.get("cases") != 52
        or differential.get("passed") != 52
        or differential.get("gcc_clang_exact") is not True
    ):
        raise RuntimeError("Inetutils compiler differential is incomplete")

    valgrind = {}
    for name in ("hostname", "dnsdomainname", "ifconfig", "whois"):
        path = artifacts[f"valgrind-{name}.log"]
        text = path.read_text(errors="replace")
        if "ERROR SUMMARY: 0 errors" not in text:
            raise RuntimeError(f"Inetutils {name} Valgrind baseline changed")
        valgrind[name] = {"errors": 0, "log_sha256": sha256(path)}

    binaries = {}
    for compiler in ("gcc", "clang"):
        compiler_root = BUILD_ROOT / f"oracle-{compiler}"
        binaries[compiler] = {}
        for name, relative in EXECUTABLES.items():
            path = compiler_root / relative
            if not path.is_file():
                raise RuntimeError(f"missing Inetutils {compiler} executable: {name}")
            dynamic = subprocess.run(
                ["readelf", "-d", str(path)], check=True, text=True,
                stdout=subprocess.PIPE,
            ).stdout
            binaries[compiler][name] = {
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
                "needed": sorted(set(re.findall(r"Shared library: \[([^]]+)\]", dynamic))),
            }

    production_lines = sum(
        len((SOURCE / name).read_text(errors="replace").splitlines())
        for name in closures["gcc"]
    )
    evidence = {
        "schema": 1,
        "recorded_at": "2026-11-23",
        "release": {
            "version": release["version"], "archive": release["archive"],
            "sha256": release["sha256"],
            "signature_sha256": release["signature_sha256"],
            "signature_verified": True,
            "signer_fingerprint": release["signer_fingerprint"],
            "signing_key_sha256": release["key_sha256"],
        },
        "scope": {
            "public_executables": sorted(EXECUTABLES),
            "clients": 16, "daemons": 10,
            "compile_actions": actions,
            "unique_production_sources": len(closures["gcc"]),
            "production_lines": production_lines,
            "production_sources": closures["gcc"],
        },
        "configuration": {
            "enabled": ["clients", "servers", "IPv4", "IPv6", "Readline", "Ncurses"],
            "disabled_optional_integrations": [
                "systemd", "PAM", "TCP wrappers", "Kerberos 4",
                "Kerberos 5", "Shishi", "IDN",
            ],
        },
        "binaries": binaries,
        "tests": {
            "gcc": suites["gcc"], "clang": suites["clang"],
            "environmental_failure": {
                "test": "hostname.sh", "operation": "sethostname",
                "reason": "container lacks CAP_SYS_ADMIN in its UTS namespace",
                "compiler_reproduced": True,
            },
            "differential": {
                "cases": 52, "passed": 52, "gcc_clang_exact": True,
            },
            "valgrind": valgrind,
        },
        "next_gate": "production-only static analysis followed by deterministic normalization and no-hole C2Rust translation",
        "artifacts": {name: sha256(path) for name, path in artifacts.items()},
    }
    output = ROOT / "evidence/inetutils-2.8-oracle.json"
    output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "applets": 26, "compile_actions": actions,
        "differential": differential["passed"],
        "production_sources": len(closures["gcc"]),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
