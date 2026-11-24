#!/usr/bin/env python3
"""Generate committed evidence for curl's unified Rustbox integration."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--link-report", type=Path, required=True)
    parser.add_argument("--report-directory", type=Path, required=True)
    parser.add_argument("--hybrid-evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    binary = args.binary.resolve()
    link = json.loads(args.link_report.read_text(encoding="utf-8"))
    hybrid = json.loads(args.hybrid_evidence.read_text(encoding="utf-8"))
    report_directory = args.report_directory.resolve()
    differential_path = report_directory / "differential.json"
    config_path = report_directory / "curl-config-differential.json"
    differential = json.loads(differential_path.read_text(encoding="utf-8"))
    config = json.loads(config_path.read_text(encoding="utf-8"))
    valgrind_paths = {
        operation: report_directory / f"valgrind-{operation}.log"
        for operation in ("version", "file")
    }

    if (
        differential.get("cases") != 12
        or differential.get("passed") != 12
        or differential.get("gcc_clang_exact") is not True
        or config.get("cases") != 24
        or config.get("passed") != 24
        or config.get("canonical_native_exact") is not True
        or link.get("curl_public_names") != 2
        or link.get("total_dispatch_names") not in (360, 499)
        or link.get("curl_config_frontend_bridge", {}).get("symbols")
        != ["rustbox_curl_config_main"]
        or not link.get("curl_namespaced_symbols")
        or sha256(binary) != link["binary"]["sha256"]
        or hybrid.get("hybrid", {}).get("translated_rust_sources") != 239
        or hybrid.get("hybrid", {}).get("canonical_c_sources") != ["lib/mprintf.c"]
    ):
        raise RuntimeError("curl multicall evidence is incomplete")

    for operation, path in valgrind_paths.items():
        text = path.read_text(errors="replace")
        zero_loss = all(marker in text for marker in (
            "definitely lost: 0 bytes", "indirectly lost: 0 bytes",
            "possibly lost: 0 bytes",
        ))
        if "ERROR SUMMARY: 0 errors" not in text or not (
            "All heap blocks were freed" in text or zero_loss
        ):
            raise RuntimeError(f"curl {operation} Valgrind result is incomplete")

    dynamic = subprocess.run(
        ["readelf", "-d", str(binary)], check=True, text=True,
        stdout=subprocess.PIPE,
    ).stdout
    needed = sorted(set(re.findall(r"Shared library: \[([^]]+)\]", dynamic)))
    curl_needed = hybrid["hybrid"]["binary"]["dynamic_needed"]
    forbidden_curl_libraries = [
        name for name in curl_needed
        if any(token in name for token in (
            "libcurl", "libssl", "libcrypto", "libssh", "libnghttp",
            "libidn", "libpsl", "libz", "libbrotli",
        ))
    ]
    if forbidden_curl_libraries:
        raise RuntimeError(
            f"curl profile has external protocol libraries: {forbidden_curl_libraries}"
        )

    evidence = {
        "schema": 1,
        "recorded_at": datetime.fromtimestamp(differential_path.stat().st_mtime, timezone.utc).date().isoformat(),
        "status": "curl and curl-config integrated at canonical parity",
        "scope": {
            "public_names": ["curl", "curl-config"],
            "stable_translated_sources": 239,
            "canonical_c_abi_residue": ["lib/mprintf.c"],
            "built_in_protocols": [
                "dict", "file", "ftp", "gopher", "http", "imap", "ipfs",
                "ipns", "mqtt", "pop3", "rtsp", "smtp", "telnet", "tftp",
                "ws",
            ],
        },
        "binary": {
            "path": str(binary),
            "bytes": binary.stat().st_size,
            "sha256": sha256(binary),
            "aggregate_multicall_needed_libraries": needed,
            "curl_profile_needed_libraries": curl_needed,
            "curl_external_protocol_libraries": [],
        },
        "link": {
            "total_dispatch_names": link["total_dispatch_names"],
            "curl_public_names": link["curl_public_names"],
            "namespaced_symbols": len(link["curl_namespaced_symbols"]),
            "curl_config_frontend_bridge": link["curl_config_frontend_bridge"],
        },
        "differential": differential,
        "curl_config_differential": config,
        "valgrind": {
            "errors": 0,
            "definitely_lost_bytes": 0,
            "indirectly_lost_bytes": 0,
            "possibly_lost_bytes": 0,
            "log_sha256": {
                operation: sha256(path)
                for operation, path in valgrind_paths.items()
            },
        },
        "report_sha256": {
            "differential": sha256(differential_path),
            "curl_config": sha256(config_path),
            "hybrid_evidence": sha256(args.hybrid_evidence),
            "link": sha256(args.link_report),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "curl_cases": differential["passed"],
        "curl_config_cases": config["passed"],
        "namespaced_symbols": len(link["curl_namespaced_symbols"]),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
