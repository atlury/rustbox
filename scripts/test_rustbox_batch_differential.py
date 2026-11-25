#!/usr/bin/env python3
"""Replay every batch differential harness against the unified Rustbox binary."""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path


def run_harness(
    command: list[str], report: Path, reuse_token: str, reuse_passing: bool = False
) -> dict[str, object]:
    report.parent.mkdir(parents=True, exist_ok=True)
    token_path = report.with_suffix(report.suffix + ".rustbox-sha256")
    if (
        reuse_passing
        and report.is_file()
        and token_path.is_file()
        and token_path.read_text(encoding="utf-8").strip() == reuse_token
    ):
        previous = json.loads(report.read_text(encoding="utf-8"))
        if previous.get("cases") == previous.get("passed"):
            return {"command": command, "status": 0, "output": "", "reused": True, "result": previous}
    report.unlink(missing_ok=True)
    token_path.unlink(missing_ok=True)
    process = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    print(process.stdout, end="")
    result: dict[str, object] = {
        "command": command,
        "status": process.returncode,
        "output": process.stdout,
    }
    if report.is_file():
        result["result"] = json.loads(report.read_text(encoding="utf-8"))
        if (
            process.returncode == 0
            and result["result"].get("cases") == result["result"].get("passed")
        ):
            token_path.write_text(reuse_token + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--coreutils-root", type=Path, required=True)
    parser.add_argument("--util-linux-build", type=Path, required=True)
    parser.add_argument("--rustbox", type=Path, required=True)
    parser.add_argument("--report-directory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--reuse-passing", action="store_true")
    parser.add_argument("--jobs", type=int, default=1)
    args = parser.parse_args()
    repository = args.repository.resolve()
    coreutils_root = args.coreutils_root.resolve()
    util_build = args.util_linux_build.resolve()
    rustbox = args.rustbox.resolve()
    rustbox_sha256 = hashlib.sha256(rustbox.read_bytes()).hexdigest()
    report_directory = args.report_directory.resolve()
    if args.jobs < 1 or args.jobs > 32:
        raise RuntimeError("--jobs must be between 1 and 32")
    jobs: list[dict[str, object]] = []

    true_false_report = report_directory / "coreutils-true-false.json"
    jobs.append({
        "suite": "coreutils",
        "batch": "true-false",
        "command": [
            "python3", str(repository / "tests/coreutils_true_false_differential.py"),
            "--canonical", str(coreutils_root / "canonical-clang-compdb/src/coreutils"),
            "--hybrid", str(rustbox), "--output", str(true_false_report),
        ],
        "report": true_false_report,
    })
    for manifest_path in sorted((repository / "batches").glob("coreutils-small-*.json")):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        batch = manifest["name"]
        report = report_directory / f"{batch}.json"
        extra = ["--exclude", "runcon", "--relocate-stdbuf"] if batch == "coreutils-small-04" else []
        jobs.append({
            "suite": "coreutils",
            "batch": batch,
            "command": [
                "python3", str(repository / "tests" / manifest["differential_harness"]),
                "--canonical", str(coreutils_root / manifest.get("canonical_build", "canonical-clang-compdb") / "src/coreutils"),
                "--hybrid", str(rustbox), "--output", str(report), *extra,
            ],
            "report": report,
        })

    temporary = tempfile.TemporaryDirectory(prefix="rustbox-unified-batches-")
    temporary_path = Path(temporary.name)
    temporary_path.chmod(0o755)
    for manifest_path in sorted((repository / "batches").glob("util-linux-small-*.json")):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        batch = manifest["name"]
        suffix = batch.removeprefix("util-linux-small-")
        invocation = temporary_path / f"rustbox-{batch}"
        invocation.symlink_to(rustbox)
        report = report_directory / f"{batch}.json"
        jobs.append({
            "suite": "util-linux",
            "batch": batch,
            "command": [
                "python3", str(repository / "tests" / f"util-linux-small-{suffix}-differential.py"),
                "--canonical-directory", str(util_build),
                "--hybrid", str(invocation), "--output", str(report),
            ],
            "report": report,
        })

    def execute(job: dict[str, object]) -> dict[str, object]:
        command = list(job["command"])
        harness_sha256 = hashlib.sha256(Path(command[1]).read_bytes()).hexdigest()
        return {
            "suite": job["suite"],
            "batch": job["batch"],
            **run_harness(
                command,
                Path(job["report"]),
                rustbox_sha256 + ":" + harness_sha256,
                args.reuse_passing,
            ),
        }

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as executor:
            records = list(executor.map(execute, jobs))
    finally:
        temporary.cleanup()

    cases = 0
    passed = 0
    failed_batches: list[str] = []
    for record in records:
        result = record.get("result")
        if not isinstance(result, dict):
            failed_batches.append(str(record["batch"]))
            continue
        cases += int(result.get("cases", 0))
        passed += int(result.get("passed", 0))
        if record["status"] != 0 or result.get("cases") != result.get("passed"):
            failed_batches.append(str(record["batch"]))
    summary = {
        "schema": 1,
        "batches": len(records),
        "cases": cases,
        "passed": passed,
        "failed_batches": failed_batches,
        "records": records,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({key: summary[key] for key in ("batches", "cases", "passed", "failed_batches")}, sort_keys=True))
    return 1 if failed_batches else 0


if __name__ == "__main__":
    raise SystemExit(main())
