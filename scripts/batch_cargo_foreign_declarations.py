#!/usr/bin/env python3
"""Verify ranked Cargo declaration candidates in parallel, retaining resumable per-archive reports."""
# SPDX-License-Identifier: 0BSD
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

from check_cargo_foreign_declarations import ROOT, digest, layout, trial
from e2fsprogs_foreign_declarations import read_proof, selection, validate_proof


def save(path, record):
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as pending:
        print(json.dumps(record, sort_keys=True), file=pending)
    Path(pending.name).replace(path)


def run(link_path, ranking_path, directory, limit, jobs, resume):
    data = link_path.read_bytes()
    link = json.loads(data)
    sha = hashlib.sha256(data).hexdigest()
    ranking = json.loads(ranking_path.read_bytes())
    if ranking["link_report_sha256"] != sha or ranking["binary_sha256"] != link["binary"]["sha256"]:
        raise ValueError("ranking belongs to a different release")
    candidates = []
    for row in ranking["archives"]:
        name = row["archive"]
        archive = Path(name)
        if name not in link["source_library_sha256"]:
            raise ValueError(f"ranking includes an unlinked archive: {name}")
        if not row["candidate_pointer_types"] or name in link.get("linked_foreign_declaration_proofs", {}):
            continue
        if not ("cargo-target" in archive.parts or archive.parent.parent.name == "target"):
            continue
        layout(archive)
        candidates.append(name)
    if len(set(candidates)) != len(candidates):
        raise ValueError("duplicate archive in ranking")
    candidates = candidates[:limit]
    plan = {"link_report_sha256": sha, "archives": candidates}
    reports = directory / "reports"
    if resume:
        if json.loads((directory / "plan.json").read_bytes()) != plan:
            raise ValueError("resume requires the same release and ranked selection")
    else:
        directory.mkdir()
        reports.mkdir()
        (directory / "logs").mkdir()
        save(directory / "plan.json", plan)

    def verify(name):
        relative = Path(name)
        # Archive stems can recur across packages. Use the complete path as the key.
        key = hashlib.sha256(name.encode()).hexdigest()
        path = reports / (key + ".json")
        if path.is_file():
            report = json.loads(path.read_bytes())
            validate_proof(link, relative, report, allow_empty=True)
            if digest(ROOT / relative) != report["archive_sha256"]:
                raise ValueError(f"archive changed since verification: {name}")
            if report["declarations_removed"]:
                selected = selection(relative, digest(path))
                read_proof(link, relative, selected)
        else:
            log_path = directory / "logs" / f"{relative.stem}-{key[:12]}.log"
            with log_path.open("wb") as log:
                report = trial(link, relative, publish=True, log=log)
            save(path, report)
        return {"status": "verified", "report": path.name, "declarations": report["declarations_removed"],
                "pointers": report["raw_pointer_type_tokens_removed"]}

    with (directory / "plan.json").open() as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        results = {}
        with ThreadPoolExecutor(max_workers=jobs) as workers:
            futures = {workers.submit(verify, name): name for name in candidates}
            for task in as_completed(futures):
                name = futures[task]
                try:
                    result = task.result()
                except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as exc:
                    result = {"status": "failed", "error": str(exc)}
                results[name] = result
                print(Path(name).stem, result, flush=True)
                save(directory / "results.json", {"link_report_sha256": sha, "archives": results})
        if link_path.read_bytes() != data:
            raise ValueError("selected release changed during verification")
        if not candidates:
            save(directory / "results.json", {"link_report_sha256": sha, "archives": {}})
        return int(any(row["status"] != "verified" for row in results.values()))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("link", type=Path)
    parser.add_argument("ranking", type=Path)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--limit", type=int, required=True)
    parser.add_argument("--jobs", type=int, default=3)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    if min(args.limit, args.jobs) < 1:
        parser.error("--limit and --jobs must be positive")
    raise SystemExit(run(args.link, args.ranking, args.directory, args.limit, args.jobs, args.resume))
