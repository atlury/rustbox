#!/usr/bin/env python3
"""Probe every selected Ncurses source independently with strict C2Rust."""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--normalization", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--jobs", type=int, default=min(8, os.cpu_count() or 1))
    args = parser.parse_args()
    records = json.loads(args.database.read_text())
    if len(records) != 264 or len({record["file"] for record in records}) != 264:
        raise RuntimeError("Ncurses C2Rust probe closure changed")
    source_root = args.source_root.resolve()
    normalization = json.loads(args.normalization.read_text())
    if (len(normalization.get("changed_sources", [])), normalization.get("entrypoints")) != (8, 7):
        raise RuntimeError("Ncurses C2Rust probe normalization changed")

    def probe(record: dict[str, object]) -> dict[str, object]:
        source = Path(str(record["file"])).resolve()
        relative = source.relative_to(source_root).as_posix()
        started = time.monotonic()
        with tempfile.TemporaryDirectory(prefix="rustbox-ncurses-c2rust-probe-") as temporary:
            root = Path(temporary)
            database = root / "compile_commands.json"
            database.write_text(json.dumps([record], indent=2) + "\n")
            result = subprocess.run(
                [
                    "c2rust", "transpile", str(database),
                    "--output-dir", str(root / "rust"),
                    "--emit-build-files", "--fail-on-error", "--disable-rustfmt",
                    "--overwrite-existing", "--preserve-unused-functions",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        return {
            "source": relative,
            "status": result.returncode,
            "passed": result.returncode == 0,
            "seconds": round(time.monotonic() - started, 3),
            "stdout_sha256": digest(result.stdout),
            "stderr_sha256": digest(result.stderr),
            "stdout": result.stdout.decode(errors="replace"),
            "stderr": result.stderr.decode(errors="replace"),
        }

    started = time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as executor:
        results = sorted(executor.map(probe, records), key=lambda item: item["source"])
    evidence = {
        "schema": 1,
        "release": "6.6",
        "status": "diagnostic only; generated outputs discarded",
        "translator": "C2Rust 0.22.1",
        "fail_on_error": True,
        "preserve_unused_functions": True,
        "compile_database_sha256": digest(args.database.read_bytes()),
        "normalization_manifest_sha256": digest(args.normalization.read_bytes()),
        "commands": len(results),
        "passed": sum(result["passed"] for result in results),
        "failed": sum(not result["passed"] for result in results),
        "jobs": args.jobs,
        "seconds": round(time.monotonic() - started, 3),
        "results": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps({key: evidence[key] for key in ("commands", "passed", "failed", "seconds")},
                     sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
