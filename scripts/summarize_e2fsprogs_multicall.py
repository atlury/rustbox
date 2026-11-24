#!/usr/bin/env python3
"""Record verified E2fsprogs integration in the global Rustbox multicall."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path


ENGINES = (
    "badblocks", "chattr", "debugfs", "dumpe2fs", "e2freefrag", "e2fsck",
    "e2image", "e2initrd_helper", "e2undo", "e4crypt", "e4defrag",
    "filefrag", "fsck", "fuse2fs", "logsave", "lsattr", "mke2fs",
    "mklost_found", "resize2fs", "tune2fs",
)
SCRIPT_ENGINES = ("compile_et", "e2scrub", "e2scrub_all", "mk_cmds")
PUBLIC_NAMES = (
    "badblocks", "chattr", "compile_et", "debugfs", "dumpe2fs",
    "e2freefrag", "e2fsck", "e2image", "e2initrd_helper", "e2label",
    "e2mmpstatus", "e2scrub", "e2scrub_all", "e2undo", "e4crypt",
    "e4defrag", "filefrag", "e2fsprogs-fsck", "fsck.ext2", "fsck.ext3", "fsck.ext4",
    "fuse2fs", "logsave", "lsattr", "mk_cmds", "mke2fs", "mkfs.ext2",
    "mkfs.ext3", "mkfs.ext4", "mklost+found", "resize2fs", "tune2fs",
)
PUBLIC_ENGINES = {
    "e2label": "tune2fs",
    "e2mmpstatus": "dumpe2fs",
    "e2fsprogs-fsck": "fsck",
    "fsck.ext2": "e2fsck",
    "fsck.ext3": "e2fsck",
    "fsck.ext4": "e2fsck",
    "mkfs.ext2": "mke2fs",
    "mkfs.ext3": "mke2fs",
    "mkfs.ext4": "mke2fs",
    "mklost+found": "mklost_found",
    **{name: name for name in ENGINES if name not in {"fsck", "mklost_found"}},
}
RUNTIME_MEMBER_COUNTS = {
    "badblocks": 211, "chattr": 193, "debugfs": 211, "dumpe2fs": 195,
    "e2freefrag": 195, "e2fsck": 195, "e2image": 195,
    "e2initrd_helper": 195, "e2undo": 195, "e4crypt": 193,
    "e4defrag": 195, "filefrag": 193, "fsck": 193, "fuse2fs": 211,
    "logsave": 193, "lsattr": 193, "mke2fs": 211, "mklost_found": 193,
    "resize2fs": 195, "tune2fs": 211,
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def defined_symbols(path: Path) -> list[str]:
    output = subprocess.run(
        ["nm", "-g", "--defined-only", str(path)], check=True,
        text=True, stdout=subprocess.PIPE,
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
    report = args.report_directory
    differential_path = report / "differential.json"
    frontend_path = report / "frontend-differential.json"
    lvm_path = report / "lvm-differential.json"
    differential = json.loads(differential_path.read_text())
    frontend = json.loads(frontend_path.read_text())
    lvm = json.loads(lvm_path.read_text())
    namespaces = link.get("e2fsprogs_namespaced_symbols", {})
    runtime_members = link.get("e2fsprogs_coalesced_runtime_members", {})
    runtime_counts = {
        name: len(members) for name, members in runtime_members.items()
    }
    bridge = link.get(
        "e2fsprogs_script_frontend_bridge",
        link.get("e2fsprogs_script_frontends_bridge", {}),
    )
    script_symbols = sorted(
        f"rustbox_e2fsprogs_{name}_main" for name in SCRIPT_ENGINES
    )
    if (
        link.get("total_dispatch_names") != 499
        or link.get("e2fsprogs_public_names") != 32
        or tuple(sorted(namespaces)) != ENGINES
        or len(namespaces) != 20
        or runtime_counts != RUNTIME_MEMBER_COUNTS
        or link.get("e2fsprogs_coalesced_runtime_member_count") != 3966
        or sorted(bridge.get("symbols", ())) != script_symbols
        or differential.get("native_names") != 28
        or differential.get("native_engines") != 20
        or differential.get("cases") != 84
        or differential.get("passed") != 84
        or differential.get("canonical_multicall_exact") is not True
        or frontend.get("programs") != 4
        or frontend.get("cases") != 24
        or frontend.get("passed") != 24
        or lvm.get("programs") != 4
        or lvm.get("cases") != 4
        or lvm.get("passed") != 4
    ):
        raise RuntimeError("E2fsprogs multicall coverage is incomplete")

    record_names = {record.get("program") for record in differential.get("records", [])}
    record_pairs = {
        (record.get("program"), record.get("engine"))
        for record in differential.get("records", [])
    }
    expected_pairs = set(PUBLIC_ENGINES.items())
    if (
        record_names != set(PUBLIC_ENGINES)
        or record_pairs != expected_pairs
        or any(
            sum(record.get("program") == name for record in differential["records"]) != 3
            for name in PUBLIC_ENGINES
        )
        or differential.get("collision_aliases") != {"fsck": "e2fsprogs-fsck"}
        or sorted(bridge.get("public_names", ())) != sorted(SCRIPT_ENGINES)
    ):
        raise RuntimeError("E2fsprogs public aliases are incomplete")

    if not args.binary.is_file():
        raise RuntimeError(f"missing Rustbox binary: {args.binary}")
    symbols = defined_symbols(args.binary)
    entrypoints = [
        *(f"rustbox_e2fsprogs_{name}_main" for name in ENGINES),
        *(f"rustbox_e2fsprogs_{name}_main" for name in SCRIPT_ENGINES),
    ]
    if any(symbols.count(symbol) != 1 for symbol in entrypoints):
        raise RuntimeError("E2fsprogs multicall entrypoints are incomplete")

    binary_record = link.get("binary", {})
    link_map = args.binary.with_suffix(".map")
    if (
        not args.binary.is_file()
        or not link_map.is_file()
        or args.binary.stat().st_size != binary_record.get("bytes")
        or sha256(args.binary) != binary_record.get("sha256")
        or sha256(link_map) != binary_record.get("link_map_sha256")
    ):
        raise RuntimeError("E2fsprogs multicall binary does not match its link report")

    valgrind: dict[str, dict[str, object]] = {}
    for name in PUBLIC_NAMES:
        path = report / f"valgrind-{name}.log"
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
            raise RuntimeError(f"E2fsprogs {name} Valgrind result is incomplete")
        valgrind[name] = {"errors": 0, "sha256": sha256(path)}

    namespace_bytes = json.dumps(
        namespaces, separators=(",", ":"), sort_keys=True
    ).encode()
    runtime_bytes = json.dumps(
        runtime_members, separators=(",", ":"), sort_keys=True
    ).encode()
    evidence = {
        "schema": 1,
        "recorded_at": "2026-11-24",
        "release": "1.47.4",
        "status": "all 32 E2fsprogs public names integrated at canonical parity",
        "dispatch": {
            "native_engines": 20,
            "script_engines": 4,
            "public_names": list(PUBLIC_NAMES),
            "public_name_count": 32,
            "collision_aliases": {"fsck": "e2fsprogs-fsck"},
            "aggregate_names": 499,
        },
        "differential": differential,
        "frontend_differential": frontend,
        "lvm_differential": lvm,
        "comparison_cases": 112,
        "comparison_passed": 112,
        "differential_sha256": sha256(differential_path),
        "frontend_differential_sha256": sha256(frontend_path),
        "lvm_differential_sha256": sha256(lvm_path),
        "valgrind": valgrind,
        "collision_isolation": {
            "program_namespaces": 20,
            "renamed_symbols": sum(len(items) for items in namespaces.values()),
            "symbol_map_sha256": hashlib.sha256(namespace_bytes).hexdigest(),
            "runtime_provider": "Procps-ng 4.0.7 pinned nightly runtime",
            "coalesced_runtime_members": 3966,
            "runtime_members_by_engine": runtime_counts,
            "runtime_member_map_sha256": hashlib.sha256(runtime_bytes).hexdigest(),
        },
        "entrypoints": entrypoints,
        "entrypoint_count": len(entrypoints),
        "script_frontend_bridge": bridge,
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
    print(json.dumps({
        "public_names": 32,
        "cases": 112,
        "valgrind": len(valgrind),
        "entrypoints": len(entrypoints),
        "binary_bytes": args.binary.stat().st_size,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
