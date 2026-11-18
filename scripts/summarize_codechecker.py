#!/usr/bin/env python3
"""Create a compact, deterministic ledger from a CodeChecker JSON export."""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import plistlib
import re
import zipfile
from pathlib import Path


ANALYZER_IN_NAME = re.compile(r"_(clangsa|clang-tidy|cppcheck)_[0-9a-f]+\.plist")


def ordered_counts(values: list[str]) -> dict[str, int]:
    return dict(sorted(collections.Counter(values).items()))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def analyzer_from_archive(path: Path) -> str:
    match = ANALYZER_IN_NAME.search(path.name)
    return match.group(1) if match else "unknown"


def failure_record(path: Path) -> dict[str, object]:
    record: dict[str, object] = {
        "archive": path.name,
        "analyzer": analyzer_from_archive(path),
        "sha256": sha256(path),
    }
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        if "return-code" in names:
            record["return_code"] = archive.read("return-code").decode(
                "utf-8", "replace"
            ).strip()
        stderr = archive.read("stderr").decode("utf-8", "replace") if "stderr" in names else ""
        stdout = archive.read("stdout").decode("utf-8", "replace") if "stdout" in names else ""
        combined = f"{stderr}\n{stdout}".lower()
        if "timed out" in combined or "time limit" in combined:
            record["classification"] = "timeout"
        elif "out of memory" in combined or "cannot allocate memory" in combined:
            record["classification"] = "out-of-memory"
        else:
            record["classification"] = "analyzer-failure"
    return record


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--export", type=Path, required=True)
    parser.add_argument("--reports", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-actions", type=int)
    args = parser.parse_args()

    exported = json.loads(args.export.read_text())
    reports = exported.get("reports")
    if exported.get("version") != 1 or not isinstance(reports, list):
        raise SystemExit("unsupported CodeChecker JSON export schema")

    completed = []
    plist_files = sorted(args.reports.glob("*.plist"))
    for path in plist_files:
        with path.open("rb") as stream:
            metadata = plistlib.load(stream).get("metadata", {})
        completed.append(metadata.get("analyzer", {}).get("name", "unknown"))

    failures = [failure_record(path) for path in sorted((args.reports / "failed").glob("*.zip"))]
    hashes = [str(report.get("report_hash", "")) for report in reports]
    unique_hashes = {item for item in hashes if item}
    actions = len(completed) + len(failures)

    summary: dict[str, object] = {
        "schema": 1,
        "codechecker_export": {
            "sha256": sha256(args.export),
            "bytes": args.export.stat().st_size,
            "schema_version": exported["version"],
        },
        "analysis_actions": {
            "completed": len(completed),
            "failed": len(failures),
            "observed": actions,
            "by_analyzer": ordered_counts(
                completed + [str(failure["analyzer"]) for failure in failures]
            ),
        },
        "diagnostics": {
            "reported": len(reports),
            "unique_context_free_hashes": len(unique_hashes),
            "by_analyzer": ordered_counts(
                [str(report.get("analyzer_name", "unknown")) for report in reports]
            ),
            "by_severity": ordered_counts(
                [str(report.get("severity", "unknown")) for report in reports]
            ),
            "by_checker": ordered_counts(
                [str(report.get("checker_name", "unknown")) for report in reports]
            ),
        },
        "failures": failures,
    }
    if args.expected_actions is not None:
        summary["analysis_actions"]["expected"] = args.expected_actions  # type: ignore[index]
        summary["analysis_actions"]["complete"] = actions == args.expected_actions  # type: ignore[index]
        if actions != args.expected_actions:
            raise SystemExit(
                f"incomplete analysis: observed {actions}, expected {args.expected_actions}"
            )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "actions": actions,
        "diagnostics": len(reports),
        "failures": len(failures),
        "unique_diagnostics": len(unique_hashes),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
