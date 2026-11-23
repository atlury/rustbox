#!/usr/bin/env python3
"""Generate committed evidence for the canonical curl 8.23.0 oracle."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ORACLE = ROOT / "work/analysis/curl-8.23.0/oracle"
SOURCE = ROOT / "work/upstream/curl-8.23.0"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalized_sources(database: Path, compiler: str) -> tuple[list[str], int]:
    records = json.loads(database.read_text())
    source_prefix = "/work/work/upstream/curl-8.23.0/"
    build_prefix = f"/rustbox-curl/oracle-{compiler}/src/"
    sources: set[str] = set()
    for record in records:
        source = str(record["file"])
        if source.startswith(source_prefix):
            sources.add(source.removeprefix(source_prefix))
        elif source.startswith(build_prefix):
            relative = source.removeprefix(build_prefix)
            if relative not in ("tool_ca_embed.c", "tool_hugehelp.c"):
                raise RuntimeError(f"unexpected generated curl source: {source}")
            sources.add("generated/src/" + relative)
        else:
            raise RuntimeError(f"curl compile source escapes signed/build roots: {source}")
    return sorted(sources), len(records)


def main() -> int:
    names = (
        "gcc-build.log", "gcc-test.log", "gcc-compile-commands.json",
        "clang-build.log", "clang-test.log", "clang-compile-commands.json",
        "config-gcc.h", "config-clang.h",
        "tool_ca_embed-gcc.c", "tool_ca_embed-clang.c",
        "tool_hugehelp-gcc.c", "tool_hugehelp-clang.c",
        "curl-gcc", "curl-clang", "curl-gcc.dynamic", "curl-clang.dynamic",
        "curl-config-gcc", "curl-config-clang", "curl-config-gcc.txt",
        "curl-config-clang.txt", "curl-config-gcc.configure.txt",
        "curl-config-clang.configure.txt", "libcurl-gcc.a", "libcurl-clang.a",
        "version-gcc.txt", "version-clang.txt", "differential.json",
        "valgrind-version.log", "valgrind-version.out",
        "valgrind-file.log", "valgrind-file.out", "file-input",
    )
    artifacts = {name: ORACLE / name for name in names}
    for path in artifacts.values():
        if not path.is_file():
            raise RuntimeError(f"missing curl oracle artifact: {path}")

    release = json.loads((ROOT / "upstream/releases.json").read_text())["releases"]["curl"]
    state = json.loads((ROOT / "work/upstream/.state/curl.json").read_text())
    for key in ("version", "sha256", "signature_sha256", "signer_fingerprint", "key_sha256"):
        if state.get(key) != release[key]:
            raise RuntimeError(f"curl source state changed at {key}")
    if not state["signature_verified"]:
        raise RuntimeError("curl release signature is not verified")

    source_sets: dict[str, list[str]] = {}
    compile_actions: dict[str, int] = {}
    for compiler in ("gcc", "clang"):
        source_sets[compiler], compile_actions[compiler] = normalized_sources(
            artifacts[f"{compiler}-compile-commands.json"], compiler
        )
    if source_sets["gcc"] != source_sets["clang"]:
        raise RuntimeError("curl compiler production closures differ")
    if compile_actions != {"gcc": 477, "clang": 477} or len(source_sets["gcc"]) != 240:
        raise RuntimeError(
            f"curl production closure changed: {compile_actions}/{len(source_sets['gcc'])}"
        )

    for compiler in ("gcc", "clang"):
        test = artifacts[f"{compiler}-test.log"].read_text(errors="replace")
        expected = (
            "TESTDONE: 2138 tests were considered",
            "TESTDONE: 1601 tests out of 1601 reported OK: 100%",
        )
        if any(fragment not in test for fragment in expected):
            raise RuntimeError(f"curl {compiler} suite totals changed")

    if artifacts["config-gcc.h"].read_bytes() != artifacts["config-clang.h"].read_bytes():
        raise RuntimeError("curl compiler configuration headers differ")
    for stem in ("tool_ca_embed", "tool_hugehelp"):
        if artifacts[f"{stem}-gcc.c"].read_bytes() != artifacts[f"{stem}-clang.c"].read_bytes():
            raise RuntimeError(f"curl generated source differs: {stem}")
    if artifacts["version-gcc.txt"].read_bytes() != artifacts["version-clang.txt"].read_bytes():
        raise RuntimeError("curl compiler version surfaces differ")
    if artifacts["curl-config-gcc.txt"].read_bytes() != artifacts["curl-config-clang.txt"].read_bytes():
        raise RuntimeError("curl-config compiler-independent surfaces differ")

    version = artifacts["version-gcc.txt"].read_text().splitlines()
    expected_protocols = [
        "dict", "file", "ftp", "gopher", "http", "imap", "ipfs", "ipns",
        "mqtt", "pop3", "rtsp", "smtp", "telnet", "tftp", "ws",
    ]
    if version[:2] != [
        "curl 8.23.0 (x86_64-pc-linux-gnu) libcurl/8.23.0",
        "Release-Date: 2026-10-14",
    ]:
        raise RuntimeError(f"curl version surface changed: {version[:2]}")
    protocols = version[2].removeprefix("Protocols: ").split()
    features = version[3].removeprefix("Features: ").split()
    if protocols != expected_protocols or features != [
        "alt-svc", "AsynchDNS", "IPv6", "Largefile", "threadsafe", "UnixSockets",
    ]:
        raise RuntimeError("curl protocol/feature surface changed")

    binaries: dict[str, dict[str, object]] = {}
    for compiler in ("gcc", "clang"):
        dynamic = artifacts[f"curl-{compiler}.dynamic"].read_text()
        needed = re.findall(r"Shared library: \[([^]]+)\]", dynamic)
        if needed != ["libc.so.6"]:
            raise RuntimeError(f"curl {compiler} gained external runtime dependencies: {needed}")
        binaries[compiler] = {
            "bytes": artifacts[f"curl-{compiler}"].stat().st_size,
            "sha256": sha256(artifacts[f"curl-{compiler}"]),
            "needed": needed,
            "static_libcurl_bytes": artifacts[f"libcurl-{compiler}.a"].stat().st_size,
            "static_libcurl_sha256": sha256(artifacts[f"libcurl-{compiler}.a"]),
        }

    differential = json.loads(artifacts["differential.json"].read_text())
    if differential["cases"] != 12 or differential["passed"] != 12:
        raise RuntimeError("curl GCC/Clang differential is incomplete")
    for name in ("valgrind-version.log", "valgrind-file.log"):
        text = artifacts[name].read_text(errors="replace")
        for expected in (
            "in use at exit: 0 bytes in 0 blocks",
            "All heap blocks were freed -- no leaks are possible",
            "ERROR SUMMARY: 0 errors from 0 contexts",
        ):
            if expected not in text:
                raise RuntimeError(f"curl Valgrind baseline changed in {name}: {expected}")
    if artifacts["file-input"].read_bytes() != artifacts["valgrind-file.out"].read_bytes():
        raise RuntimeError("curl Valgrind file transfer changed payload")

    production_lines = 0
    for name in source_sets["gcc"]:
        if name == "generated/src/tool_ca_embed.c":
            path = artifacts["tool_ca_embed-gcc.c"]
        elif name == "generated/src/tool_hugehelp.c":
            path = artifacts["tool_hugehelp-gcc.c"]
        else:
            path = SOURCE / name
        production_lines += len(path.read_text(errors="replace").splitlines())

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
            "public_interfaces": ["curl", "curl-config"],
            "runtime": "static libcurl",
            "compile_actions": compile_actions,
            "unique_production_sources": len(source_sets["gcc"]),
            "production_lines": production_lines,
            "production_sources": source_sets["gcc"],
        },
        "configuration": {
            "policy": "no external package runtime; libc and POSIX threads only",
            "protocols": protocols, "features": features,
            "disabled_external_components": [
                "TLS", "zlib", "brotli", "zstd", "PSL", "GSASL", "SSH",
                "IDN", "GSS-API", "LDAP", "HTTP/2", "HTTP/3", "libuv",
            ],
            "curl_config_compiler_specific_provenance": {
                compiler: artifacts[f"curl-config-{compiler}.configure.txt"].read_text().strip()
                for compiler in ("gcc", "clang")
            },
        },
        "binaries": binaries,
        "tests": {
            "gcc": {"considered": 2138, "applicable": 1601, "passed": 1601},
            "clang": {"considered": 2138, "applicable": 1601, "passed": 1601},
            "differential": {"cases": 12, "passed": 12, "gcc_clang_exact": True},
            "valgrind": {
                "paths": ["--version", "file transfer"],
                "errors": 0, "bytes_in_use_at_exit": 0,
            },
        },
        "next_gate": "production-only static analysis followed by deterministic normalization and no-hole C2Rust translation",
        "artifacts": {name: sha256(path) for name, path in artifacts.items()},
    }
    output = ROOT / "evidence/curl-8.23.0-oracle.json"
    output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "compile_actions": compile_actions, "differential": 12,
        "production_sources": len(source_sets["gcc"]), "suite_passes": 3202,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
