#!/usr/bin/env python3
"""Record verified IPRoute2 integration in the global Rustbox multicall."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path


ENGINES = (
    "arpd", "bridge", "dcb", "devlink", "dpll", "genl", "ifstat", "ip",
    "lnstat", "netshaper", "nstat", "rdma", "rtacct", "rtmon", "ss", "tc",
    "tipc", "vdpa",
)
PUBLIC_NAMES = (*ENGINES, "ctstat", "rtstat", "routel")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def defined_symbols(path: Path) -> list[str]:
    output = subprocess.run(
        ["nm", "-g", "--defined-only", str(path)],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout
    return [line.split()[-1] for line in output.splitlines() if line.split()]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", required=True, type=Path)
    parser.add_argument("--link-report", required=True, type=Path)
    parser.add_argument("--report-directory", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    link = json.loads(args.link_report.read_text())
    differential_path = args.report_directory / "differential.json"
    differential = json.loads(differential_path.read_text())
    namespaces = link.get("iproute2_namespaced_symbols", {})
    bridge = link.get("iproute2_routel_frontend_bridge", {})
    if (
        link.get("total_dispatch_names") not in (467, 499)
        or link.get("iproute2_public_names") != 21
        or tuple(namespaces) != ENGINES
        or len(namespaces) != 18
        or bridge.get("symbols") != ["rustbox_iproute2_routel_main"]
        or bridge.get("public_names") != ["routel"]
        or differential.get("public_name_count") != 21
        or tuple(differential.get("public_names", ())) != PUBLIC_NAMES
        or differential.get("translated_engines") != 18
        or differential.get("cases") != 66
        or differential.get("passed") != 66
        or differential.get("canonical_multicall_exact") is not True
    ):
        raise RuntimeError("IPRoute2 multicall coverage is incomplete")

    symbols = defined_symbols(args.binary)
    entrypoints = [
        *(f"rustbox_iproute2_{name}_main" for name in ENGINES),
        "rustbox_iproute2_routel_main",
    ]
    if any(symbols.count(symbol) != 1 for symbol in entrypoints):
        raise RuntimeError("IPRoute2 multicall entrypoints are incomplete")

    binary_record = link.get("binary", {})
    link_map = args.binary.with_suffix(".map")
    if (
        not args.binary.is_file()
        or not link_map.is_file()
        or args.binary.stat().st_size != binary_record.get("bytes")
        or sha256(args.binary) != binary_record.get("sha256")
        or sha256(link_map) != binary_record.get("link_map_sha256")
    ):
        raise RuntimeError("IPRoute2 multicall binary does not match its link report")

    valgrind: dict[str, dict[str, object]] = {}
    for name in PUBLIC_NAMES:
        path = args.report_directory / f"valgrind-{name}.log"
        text = path.read_text(errors="replace")
        match = re.search(r"ERROR SUMMARY: (\d+) errors", text)
        zero_loss = all(
            marker in text
            for marker in (
                "definitely lost: 0 bytes",
                "indirectly lost: 0 bytes",
                "possibly lost: 0 bytes",
            )
        )
        if match is None or int(match.group(1)) != 0 or not (
            "All heap blocks were freed -- no leaks are possible" in text or zero_loss
        ):
            raise RuntimeError(f"IPRoute2 {name} Valgrind result is incomplete")
        valgrind[name] = {"errors": 0, "sha256": sha256(path)}

    namespace_bytes = json.dumps(
        namespaces, separators=(",", ":"), sort_keys=True
    ).encode()
    evidence = {
        "schema": 1,
        "recorded_at": datetime.fromtimestamp(differential_path.stat().st_mtime, timezone.utc).date().isoformat(),
        "release": "7.3.0",
        "status": "all 21 IPRoute2 public names integrated at canonical parity",
        "dispatch": {
            "translated_engines": 18,
            "public_names": list(PUBLIC_NAMES),
            "public_name_count": 21,
            "aliases": {"ctstat": "lnstat", "rtstat": "lnstat"},
            "aggregate_names": link["total_dispatch_names"],
        },
        "differential": differential,
        "differential_sha256": sha256(differential_path),
        "valgrind": valgrind,
        "collision_isolation": {
            "program_namespaces": 18,
            "renamed_symbols": sum(len(items) for items in namespaces.values()),
            "symbol_map_sha256": hashlib.sha256(namespace_bytes).hexdigest(),
        },
        "entrypoints": entrypoints,
        "entrypoint_count": len(entrypoints),
        "routel_frontend_bridge": bridge,
        "link_report_sha256": sha256(args.link_report),
        "binary": {
            **binary_record,
            "verified_bytes": args.binary.stat().st_size,
            "verified_sha256": sha256(args.binary),
            "verified_link_map_sha256": sha256(link_map),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                "public_names": 21,
                "cases": 66,
                "valgrind": len(valgrind),
                "entrypoints": len(entrypoints),
                "binary_bytes": args.binary.stat().st_size,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
